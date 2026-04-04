"""rag — Retrieval-Augmented Generation: book RAG, rule extraction, case retrieval."""

from .loaders import Document, TextLoader, PDFLoader, JSONLoader, DirectoryLoader
from .chunker import Chunk, SmartChunker, VerseAwareChunker, SlidingWindowChunker
from .vector_store import VectorStore, SearchResult
from .embedder import Embedder, get_embedder
from .rule_extractor import ExtractedRule, RuleExtractor, regex_extract_rules
from .rule_retriever import RuleRetriever, retrieve_rules_for_domain
from .case_ingester import CaseRecord, CaseIngester
from .case_retriever import CaseRetriever, build_case_index

__all__ = [
    # Loaders
    "Document", "TextLoader", "PDFLoader", "JSONLoader", "DirectoryLoader",
    # Chunking
    "Chunk", "SmartChunker", "VerseAwareChunker", "SlidingWindowChunker",
    # Vector store
    "VectorStore", "SearchResult",
    # Embedder
    "Embedder", "get_embedder",
    # Rule extraction
    "ExtractedRule", "RuleExtractor", "regex_extract_rules",
    # Rule retrieval
    "RuleRetriever", "retrieve_rules_for_domain",
    # Case ingestion
    "CaseRecord", "CaseIngester",
    # Case retrieval
    "CaseRetriever", "build_case_index",
]
