package com.veritymesh.platform.knowledge;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Objects;
import java.util.regex.Pattern;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;

/**
 * Source Zone adapter backed by an S3-compatible object store.
 *
 * <p>The domain layer only receives a short-lived upload URL and verified
 * metadata. Provider SDK requests, credentials and object-store errors stay
 * inside this adapter.</p>
 */
public final class S3SourceStorage implements SourceStorage, AutoCloseable {

    private static final int BUFFER_SIZE = 16 * 1024;
    private static final Pattern CONTROL_CHARACTER = Pattern.compile("[\\p{Cntrl}]");

    private final SourceStorageProperties properties;
    private final S3Client s3Client;
    private final S3Presigner presigner;

    public S3SourceStorage(SourceStorageProperties properties) {
        this(
                properties,
                buildClient(properties),
                buildPresigner(properties));
    }

    S3SourceStorage(SourceStorageProperties properties, S3Client s3Client, S3Presigner presigner) {
        this.properties = Objects.requireNonNull(properties, "properties");
        this.s3Client = Objects.requireNonNull(s3Client, "s3Client");
        this.presigner = Objects.requireNonNull(presigner, "presigner");
        validateConfiguration(properties);
    }

    @Override
    public String sourceZoneKey(String projectId, String sourceObjectId, String sourceRevisionId) {
        String projectSegment = HexFormat.of().formatHex(
                sha256Digest().digest(requireValue(projectId, "projectId").getBytes(StandardCharsets.UTF_8)));
        String key = trimSlashes(properties.getPathPrefix()) + "/"
                + projectSegment + "/"
                + requireIdentifier(sourceObjectId, "sourceObjectId") + "/"
                + requireIdentifier(sourceRevisionId, "sourceRevisionId");
        return validateKey(key);
    }

    @Override
    public UploadReservation reserveUpload(String sourceZoneKey, String contentType, long contentLength) {
        String key = validateKey(sourceZoneKey);
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("contentType must not be blank");
        }
        if (contentLength < 0) {
            throw new IllegalArgumentException("contentLength must not be negative");
        }

        PutObjectRequest putObject = PutObjectRequest.builder()
                .bucket(properties.getBucket())
                .key(key)
                .contentType(contentType)
                .contentLength(Long.valueOf(contentLength))
                .build();
        try {
            Duration signatureDuration = properties.getPresignDuration();
            PresignedPutObjectRequest presigned = presigner.presignPutObject(PutObjectPresignRequest.builder()
                    .signatureDuration(signatureDuration)
                    .putObjectRequest(putObject)
                    .build());
            return new UploadReservation(presigned.url().toExternalForm(), presigned.expiration());
        } catch (SdkClientException | S3Exception error) {
            throw new SourceStorageAccessException("source upload URL could not be created", error);
        }
    }

    @Override
    public UploadedObject verifyUploaded(String sourceZoneKey) {
        String key = validateKey(sourceZoneKey);
        HeadObjectResponse head = headObject(key);
        String contentType = Objects.requireNonNullElse(head.contentType(), "");
        long headLength = head.contentLength();

        try (ResponseInputStream<GetObjectResponse> input = s3Client.getObject(GetObjectRequest.builder()
                .bucket(properties.getBucket())
                .key(key)
                .build())) {
            HashAndLength hashAndLength = sha256(input);
            GetObjectResponse response = input.response();
            if (hashAndLength.length() != headLength
                    || !Objects.equals(response.contentLength(), headLength)
                    || !Objects.equals(response.contentType(), contentType)) {
                throw new SourceStorageAccessException(
                        "source object changed while it was being verified", null);
            }
            return new UploadedObject(hashAndLength.sha256(), contentType, headLength);
        } catch (S3Exception error) {
            throw mapStorageException(error);
        } catch (SdkClientException | IOException error) {
            throw new SourceStorageAccessException("source object could not be verified", error);
        }
    }

    @Override
    public void close() {
        presigner.close();
        s3Client.close();
    }

    private HeadObjectResponse headObject(String key) {
        try {
            return s3Client.headObject(HeadObjectRequest.builder()
                    .bucket(properties.getBucket())
                    .key(key)
                    .build());
        } catch (S3Exception error) {
            throw mapStorageException(error);
        } catch (SdkClientException error) {
            throw new SourceStorageAccessException("source object metadata could not be read", error);
        }
    }

    private RuntimeException mapStorageException(RuntimeException error) {
        if (isNotFound(error)) {
            return new SourceObjectNotFoundException();
        }
        return new SourceStorageAccessException("source object could not be read", error);
    }

    private static boolean isNotFound(RuntimeException error) {
        if (error instanceof S3Exception s3Exception) {
            return s3Exception.statusCode() == 404;
        }
        return false;
    }

    private static HashAndLength sha256(InputStream input) throws IOException {
        MessageDigest digest = sha256Digest();
        byte[] buffer = new byte[BUFFER_SIZE];
        long length = 0;
        int read;
        while ((read = input.read(buffer)) != -1) {
            digest.update(buffer, 0, read);
            length += read;
        }
        return new HashAndLength(HexFormat.of().formatHex(digest.digest()), length);
    }

    private String validateKey(String sourceZoneKey) {
        if (sourceZoneKey == null || sourceZoneKey.isBlank()) {
            throw new IllegalArgumentException("sourceZoneKey must not be blank");
        }
        if (CONTROL_CHARACTER.matcher(sourceZoneKey).find()
                || sourceZoneKey.startsWith("/")
                || sourceZoneKey.contains("\\")
                || sourceZoneKey.contains("//")) {
            throw new IllegalArgumentException("sourceZoneKey contains an unsafe path");
        }
        for (String segment : sourceZoneKey.split("/", -1)) {
            if (segment.equals(".") || segment.equals("..") || segment.isBlank()) {
                throw new IllegalArgumentException("sourceZoneKey contains an unsafe path");
            }
        }
        String prefix = trimSlashes(properties.getPathPrefix());
        if (!prefix.isEmpty() && !(sourceZoneKey.equals(prefix) || sourceZoneKey.startsWith(prefix + "/"))) {
            throw new IllegalArgumentException("sourceZoneKey is outside the Source Zone prefix");
        }
        return sourceZoneKey;
    }

    private static String trimSlashes(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        return value.replaceAll("^/+|/+$", "");
    }

    private static String requireValue(String value, String field) {
        if (value == null || value.isBlank() || CONTROL_CHARACTER.matcher(value).find()) {
            throw new IllegalArgumentException(field + " contains an unsafe identifier");
        }
        return value;
    }

    private static String requireIdentifier(String value, String field) {
        if (value == null || value.isBlank() || CONTROL_CHARACTER.matcher(value).find()
                || value.contains("/") || value.contains("\\")
                || value.equals(".") || value.equals("..")) {
            throw new IllegalArgumentException(field + " contains an unsafe identifier");
        }
        return value;
    }

    private static MessageDigest sha256Digest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is not available", error);
        }
    }

    private static void validateConfiguration(SourceStorageProperties properties) {
        requireNonBlank(properties.getEndpoint(), "endpoint");
        requireNonBlank(properties.getRegion(), "region");
        requireNonBlank(properties.getBucket(), "bucket");
        requireNonBlank(properties.getPathPrefix(), "pathPrefix");
        requireNonBlank(properties.getAccessKey(), "accessKey");
        requireNonBlank(properties.getSecretKey(), "secretKey");
        if (properties.getPresignDuration() == null
                || properties.getPresignDuration().isNegative()
                || properties.getPresignDuration().isZero()) {
            throw new IllegalStateException("source storage presignDuration must be positive");
        }
        try {
            URI endpoint = URI.create(properties.getEndpoint());
            if (!endpoint.isAbsolute()
                    || endpoint.getHost() == null
                    || !("http".equalsIgnoreCase(endpoint.getScheme())
                            || "https".equalsIgnoreCase(endpoint.getScheme()))) {
                throw new IllegalArgumentException("endpoint must be an absolute http(s) URI");
            }
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException("source storage endpoint is not a valid URI", error);
        }
    }

    private static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("source storage " + field + " must be configured when enabled");
        }
    }

    private static S3Client buildClient(SourceStorageProperties properties) {
        validateConfiguration(properties);
        StaticCredentialsProvider credentials = StaticCredentialsProvider.create(
                AwsBasicCredentials.create(properties.getAccessKey(), properties.getSecretKey()));
        return S3Client.builder()
                .endpointOverride(URI.create(properties.getEndpoint()))
                .region(software.amazon.awssdk.regions.Region.of(properties.getRegion()))
                .credentialsProvider(credentials)
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(properties.isForcePathStyle())
                        .build())
                .build();
    }

    private static S3Presigner buildPresigner(SourceStorageProperties properties) {
        validateConfiguration(properties);
        StaticCredentialsProvider credentials = StaticCredentialsProvider.create(
                AwsBasicCredentials.create(properties.getAccessKey(), properties.getSecretKey()));
        return S3Presigner.builder()
                .endpointOverride(URI.create(properties.getEndpoint()))
                .region(software.amazon.awssdk.regions.Region.of(properties.getRegion()))
                .credentialsProvider(credentials)
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(properties.isForcePathStyle())
                        .build())
                .build();
    }

    private record HashAndLength(String sha256, long length) {
    }
}
