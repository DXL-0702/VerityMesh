package com.veritymesh.platform.knowledge;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "projects")
public class ProjectEntity {

    @Id
    @Column(length = 256, nullable = false)
    private String id;

    protected ProjectEntity() {
    }
}
