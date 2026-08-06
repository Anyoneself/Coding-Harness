"""Milvus 向量知识仓储。"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Iterable
from typing import Any

from ..domain.models import RetrievalHit
from ..infrastructure.security import inspect_untrusted_content
from .knowledge import KnowledgeDocument, SearchDiagnostics, tokenize


class MilvusKnowledgeBase:
    """使用本地哈希向量和 Milvus COSINE 索引检索通用知识文档。"""

    def __init__(
        self,
        *,
        uri: str,
        collection_name: str,
        documents: Iterable[KnowledgeDocument],
        token: str = "",
        dimension: int = 256,
        client: Any | None = None,
    ) -> None:
        """保存连接与集合配置，并延迟到首次查询时创建索引和默认数据。"""
        self.uri = uri
        self.token = token
        self.collection_name = collection_name
        self.dimension = dimension
        self._documents = tuple(documents)
        self._client = client
        self._active_version = 1
        self._initialized = False
        self._lock = threading.RLock()

    @property
    def active_version(self) -> int:
        """连接 Milvus 后返回集合中当前最大的知识版本。"""
        self._ensure_collection()
        return self._active_version

    def replace_documents(self, documents: Iterable[KnowledgeDocument]) -> int:
        """把新文档作为下一知识版本写入 Milvus，并原子切换进程内活动版本。"""
        self._ensure_collection()
        with self._lock:
            next_version = self._active_version + 1
            document_list = tuple(documents)
            if not document_list:
                raise ValueError("knowledge index cannot be empty")
            self._upsert_documents(document_list, next_version)
            self._active_version = next_version
            return next_version

    def search(
        self,
        query: str,
        allowed_domains: set[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievalHit], SearchDiagnostics]:
        """在 Milvus 中执行向量检索，并对返回内容实施不可信数据隔离。"""
        self._ensure_collection()
        query_vector = self._embed(query)
        if not any(query_vector):
            return [], self._diagnostics(0)

        expression = f"knowledge_version == {self._active_version}"
        if allowed_domains:
            domains = ", ".join(json.dumps(item, ensure_ascii=False) for item in allowed_domains)
            expression += f" and domain in [{domains}]"
        raw_results = self._client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="vector",
            filter=expression,
            limit=max(1, min(top_k, 20)),
            output_fields=[
                "document_id",
                "source_type",
                "domain",
                "title",
                "content",
                "source",
                "authority",
                "knowledge_version",
            ],
        )
        result_group = raw_results[0] if raw_results else []
        hits: list[RetrievalHit] = []
        for item in result_group:
            entity = item.get("entity") or {}
            safe_content, flags = inspect_untrusted_content(str(entity.get("content") or ""))
            score = round(float(item.get("distance") or 0.0), 6)
            hits.append(
                RetrievalHit(
                    document_id=str(entity.get("document_id") or item.get("id") or ""),
                    source_type=str(entity.get("source_type") or "knowledge"),
                    domain=str(entity.get("domain") or "通用资料"),
                    title=str(entity.get("title") or ""),
                    content=safe_content,
                    source=str(entity.get("source") or ""),
                    sparse_score=0.0,
                    dense_score=score,
                    fused_score=score,
                    knowledge_version=int(
                        entity.get("knowledge_version") or self._active_version
                    ),
                    security_flags=flags,
                )
            )
        return hits, self._diagnostics(len(hits))

    def drop_collection(self) -> None:
        """删除当前 Milvus 集合，供隔离集成测试和显式清理使用。"""
        client = self._get_client()
        if client.has_collection(collection_name=self.collection_name):
            client.drop_collection(collection_name=self.collection_name)
        self._initialized = False

    def close(self) -> None:
        """幂等关闭已经创建的 Milvus 客户端连接。"""
        with self._lock:
            if self._client is None:
                return
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None
            self._initialized = False

    def _ensure_collection(self) -> None:
        """以线程安全方式创建或加载集合，并在空集合中写入默认文档。"""
        with self._lock:
            if self._initialized:
                return
            client = self._get_client()
            if not client.has_collection(collection_name=self.collection_name):
                from pymilvus import DataType

                client.create_collection(
                    collection_name=self.collection_name,
                    dimension=self.dimension,
                    primary_field_name="document_id",
                    id_type=DataType.VARCHAR,
                    vector_field_name="vector",
                    metric_type="COSINE",
                    auto_id=False,
                    max_length=512,
                    consistency_level="Strong",
                )
            versions = client.query(
                collection_name=self.collection_name,
                filter="",
                output_fields=["knowledge_version"],
                limit=16384,
            )
            if versions:
                self._active_version = max(
                    int(item.get("knowledge_version") or 1) for item in versions
                )
            else:
                self._upsert_documents(self._documents, self._active_version)
            self._initialized = True

    def _upsert_documents(
        self,
        documents: Iterable[KnowledgeDocument],
        version: int,
    ) -> None:
        """把一批知识文档转换为动态字段实体并写入 Milvus。"""
        entities = [
            {
                "document_id": document.id,
                "vector": self._embed(f"{document.title} {document.content}"),
                "source_type": document.source_type,
                "domain": document.domain,
                "title": document.title,
                "content": document.content[:60000],
                "source": document.source,
                "resolved": document.resolved,
                "authority": document.authority,
                "knowledge_version": version,
            }
            for document in documents
        ]
        if not entities:
            raise ValueError("knowledge index cannot be empty")
        self._client.upsert(collection_name=self.collection_name, data=entities)
        self._client.flush(collection_name=self.collection_name)

    def _diagnostics(self, candidates: int) -> SearchDiagnostics:
        """读取 Milvus 行数并生成与本地知识库一致的诊断结构。"""
        stats = self._client.get_collection_stats(collection_name=self.collection_name)
        return SearchDiagnostics(
            knowledge_version=self._active_version,
            total_documents=int(stats.get("row_count") or 0),
            candidate_documents=candidates,
            fusion_method="milvus_cosine",
        )

    def _get_client(self) -> Any:
        """延迟创建 MilvusClient，避免应用导入阶段依赖外部服务可用性。"""
        if self._client is not None:
            return self._client
        from pymilvus import MilvusClient

        options: dict[str, str] = {"uri": self.uri}
        if self.token:
            options["token"] = self.token
        self._client = MilvusClient(**options)
        return self._client

    def _embed(self, text: str) -> list[float]:
        """生成确定性的归一化哈希向量，避免本地检索依赖外部 Embedding API。"""
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
