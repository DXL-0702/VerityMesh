package com.veritymesh.platform.knowledge;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OutboxEventRepository extends JpaRepository<OutboxEventEntity, String> {

    List<OutboxEventEntity> findByPublishedAtIsNullOrderByOccurredAtAsc(Pageable pageable);
}
