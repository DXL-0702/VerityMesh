package com.veritymesh.platform.knowledge;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SourceRevisionRepository extends JpaRepository<SourceRevisionEntity, String> {

    Optional<SourceRevisionEntity> findByProjectIdAndIdempotencyKey(String projectId, String idempotencyKey);

}
