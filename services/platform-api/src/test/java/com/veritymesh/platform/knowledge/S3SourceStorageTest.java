package com.veritymesh.platform.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;
import static org.assertj.core.api.Assertions.assertThatIllegalStateException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.URL;
import java.time.Duration;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

class S3SourceStorageTest {

    @Test
    void createsShortLivedPutReservationForTheConfiguredBucketAndKey() throws Exception {
        S3Client client = mock(S3Client.class);
        S3Presigner presigner = mock(S3Presigner.class);
        PresignedPutObjectRequest signed = mock(PresignedPutObjectRequest.class);
        URL signedUrl = URI.create("http://localhost:19000/veritymesh-source/source-zone/project/revision"
                + "?X-Amz-Signature=test").toURL();
        when(presigner.presignPutObject(any(PutObjectPresignRequest.class))).thenReturn(signed);
        when(signed.url()).thenReturn(signedUrl);
        when(signed.expiration()).thenReturn(java.time.Instant.parse("2026-08-14T01:00:00Z"));

        S3SourceStorage storage = new S3SourceStorage(properties(), client, presigner);
        SourceStorage.UploadReservation reservation = storage.reserveUpload(
                "source-zone/project/revision", "application/pdf", 42);

        assertThat(reservation.uploadUrl()).isEqualTo(signedUrl.toExternalForm());
        assertThat(reservation.expiresAt()).isEqualTo(java.time.Instant.parse("2026-08-14T01:00:00Z"));

        ArgumentCaptor<PutObjectPresignRequest> request = ArgumentCaptor.forClass(PutObjectPresignRequest.class);
        verify(presigner).presignPutObject(request.capture());
        assertThat(request.getValue().putObjectRequest().bucket()).isEqualTo("veritymesh-source");
        assertThat(request.getValue().putObjectRequest().key()).isEqualTo("source-zone/project/revision");
        assertThat(request.getValue().putObjectRequest().contentType()).isEqualTo("application/pdf");
        assertThat(request.getValue().putObjectRequest().contentLength()).isEqualTo(42L);
        assertThat(request.getValue().signatureDuration()).isEqualTo(Duration.ofMinutes(15));
    }

    @Test
    void generatesAnIsolatedKeyFromTheConfiguredPrefixWithoutUsingTheProjectPath() {
        S3SourceStorage storage = new S3SourceStorage(properties(), mock(S3Client.class), mock(S3Presigner.class));

        String key = storage.sourceZoneKey("project/with/a/path", "source-object-1", "source-revision-1");

        assertThat(key).startsWith("source-zone/")
                .endsWith("/source-object-1/source-revision-1")
                .doesNotContain("project/with/a/path");
    }

    @Test
    void streamsTheObjectToComputeSha256AndReturnsHeadMetadata() throws Exception {
        S3Client client = mock(S3Client.class);
        S3Presigner presigner = mock(S3Presigner.class);
        byte[] content = "hello source".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        when(client.headObject(any(HeadObjectRequest.class))).thenReturn(HeadObjectResponse.builder()
                .contentType("text/plain")
                .contentLength((long) content.length)
                .build());
        when(client.getObject(any(GetObjectRequest.class))).thenReturn(new ResponseInputStream<>(
                GetObjectResponse.builder().contentLength((long) content.length).contentType("text/plain").build(),
                new ByteArrayInputStream(content)));

        S3SourceStorage storage = new S3SourceStorage(properties(), client, presigner);
        SourceStorage.UploadedObject uploaded = storage.verifyUploaded("source-zone/project/revision");

        assertThat(uploaded.contentSha256()).isEqualTo(HexFormat.of().formatHex(
                java.security.MessageDigest.getInstance("SHA-256").digest(content)));
        assertThat(uploaded.contentType()).isEqualTo("text/plain");
        assertThat(uploaded.contentLength()).isEqualTo(content.length);
        ArgumentCaptor<GetObjectRequest> request = ArgumentCaptor.forClass(GetObjectRequest.class);
        verify(client).getObject(request.capture());
        assertThat(request.getValue().bucket()).isEqualTo("veritymesh-source");
        assertThat(request.getValue().key()).isEqualTo("source-zone/project/revision");
    }

    @Test
    void rejectsUnsafeOrOutOfZoneKeysBeforeCallingTheProvider() {
        S3Client client = mock(S3Client.class);
        S3Presigner presigner = mock(S3Presigner.class);
        S3SourceStorage storage = new S3SourceStorage(properties(), client, presigner);

        assertThatIllegalArgumentException()
                .isThrownBy(() -> storage.reserveUpload("source-zone/../escape", "text/plain", 1));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> storage.reserveUpload("other-zone/project/revision", "text/plain", 1));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> storage.reserveUpload("source-zone/project\\revision", "text/plain", 1));
    }

    @Test
    void mapsMissingObjectsAndProviderFailuresWithoutLeakingSdkTypes() {
        S3Client client = mock(S3Client.class);
        S3Presigner presigner = mock(S3Presigner.class);
        S3SourceStorage storage = new S3SourceStorage(properties(), client, presigner);

        when(client.headObject(any(HeadObjectRequest.class)))
                .thenThrow(S3Exception.builder().statusCode(404).build());
        assertThatThrownBy(() -> storage.verifyUploaded("source-zone/project/revision"))
                .isInstanceOf(SourceObjectNotFoundException.class);

        when(client.headObject(any(HeadObjectRequest.class)))
                .thenThrow(S3Exception.builder().statusCode(503).build());
        assertThatThrownBy(() -> storage.verifyUploaded("source-zone/project/revision"))
                .isInstanceOf(SourceStorageAccessException.class)
                .hasMessageContaining("could not be read");
    }

    @Test
    void enabledAdapterRequiresCredentialsAndValidEndpoint() {
        SourceStorageProperties missingCredentials = properties();
        missingCredentials.setSecretKey("");
        assertThatIllegalStateException()
                .isThrownBy(() -> new S3SourceStorage(missingCredentials, mock(S3Client.class), mock(S3Presigner.class)))
                .withMessageContaining("secretKey");

        SourceStorageProperties invalidEndpoint = properties();
        invalidEndpoint.setEndpoint("not-a-uri");
        assertThatIllegalStateException()
                .isThrownBy(() -> new S3SourceStorage(invalidEndpoint, mock(S3Client.class), mock(S3Presigner.class)))
                .withMessageContaining("endpoint");
    }

    @Test
    void buildsTheRealSdkClientsWithTheLocalCompatibilitySettings() {
        try (S3SourceStorage ignored = new S3SourceStorage(properties())) {
            assertThat(ignored).isNotNull();
        }
    }

    @Test
    void disabledConfigurationKeepsTheFailClosedStorageBaseline() {
        SourceStorageProperties disabled = properties();
        disabled.setEnabled(false);
        SourceStorage storage = new KnowledgeConfiguration().sourceStorage(disabled);

        assertThat(storage).isInstanceOf(UnavailableSourceStorage.class);
        assertThatThrownBy(() -> storage.reserveUpload("source-zone/project/revision", "text/plain", 1))
                .isInstanceOf(SourceStorageNotConfigured.class);
    }

    private static SourceStorageProperties properties() {
        SourceStorageProperties properties = new SourceStorageProperties();
        properties.setEnabled(true);
        properties.setEndpoint("http://localhost:19000");
        properties.setRegion("us-east-1");
        properties.setBucket("veritymesh-source");
        properties.setAccessKey("veritymesh-source");
        properties.setSecretKey("veritymesh-source-local-secret");
        properties.setPresignDuration(Duration.ofMinutes(15));
        properties.setPathPrefix("source-zone");
        properties.setForcePathStyle(true);
        return properties;
    }
}
