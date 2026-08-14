"""GLB asset analysis schemas (Phase 2.5-B) - mirror of src/shared/types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class GlbBounds(_CamelModel):
    min: list[float]
    max: list[float]


class GlbDimensions(_CamelModel):
    x: float
    y: float
    z: float


class GlbCenter(_CamelModel):
    x: float
    y: float
    z: float


class MeshStat(_CamelModel):
    name: str
    index: int
    vertex_count: int = Field(alias="vertexCount")
    index_count: int = Field(alias="indexCount")
    triangle_count: int = Field(alias="triangleCount")
    material_index: int | None = Field(default=None, alias="materialIndex")
    has_normals: bool = Field(alias="hasNormals")
    has_uvs: bool = Field(alias="hasUVs")
    mode: int = 4


class GlbStats(_CamelModel):
    format: str = "glb"
    version: int = 2
    size_bytes: int = Field(alias="sizeBytes")
    mesh_count: int = Field(alias="meshCount")
    primitive_count: int = Field(alias="primitiveCount")
    vertex_count: int = Field(alias="vertexCount")
    index_count: int = Field(alias="indexCount")
    triangle_count: int = Field(alias="triangleCount")
    material_count: int = Field(alias="materialCount")
    texture_count: int = Field(alias="textureCount")
    has_normals: bool = Field(alias="hasNormals")
    has_uvs: bool = Field(alias="hasUVs")
    bounds: GlbBounds | None = None
    dimensions: GlbDimensions | None = None
    center: GlbCenter | None = None
    mesh_stats: list[MeshStat] = Field(default_factory=list, alias="meshStats")
    warnings: list[str] = Field(default_factory=list)
    # Phase 2.7-D: whether the GLB carries a `skins` entry (skinned mesh).
    # Optional field; old stats without it remain valid.
    skinned: bool = False
