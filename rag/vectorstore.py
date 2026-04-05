"""
ChromaDB Vector Store for Job Hunter RAG
Stores CV chunks and job descriptions for context retrieval
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class JobVectorStore:
    """
    ChromaDB-based vector store for RAG cover letter generation.
    Same pattern as ops-pilot-ai - demonstrates RAG in production.
    """
    
    def __init__(self, persist_dir: str = "./chroma_db"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize embedding model (all-MiniLM-L6-v2 - fast and good)
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Create collections
        self._init_collections()
    
    def _init_collections(self):
        """Initialize or get existing collections"""
        # CV collection - stores CV chunks for personalization
        self.cv_collection = self.client.get_or_create_collection(
            name="cv_chunks",
            metadata={"description": "CV content for cover letter personalization"}
        )
        
        # Job descriptions collection - for similar job matching
        self.jobs_collection = self.client.get_or_create_collection(
            name="job_descriptions",
            metadata={"description": "Job descriptions for context matching"}
        )
    
    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts"""
        return self.embedder.encode(texts).tolist()
    
    def add_cv_chunks(self, chunks: List[Dict[str, str]], clear_existing: bool = False):
        """
        Add CV chunks to the vector store.
        
        Args:
            chunks: List of {"id": str, "text": str, "metadata": dict}
            clear_existing: If True, clear existing CV chunks first
        """
        if clear_existing:
            # Delete all existing CV chunks
            existing = self.cv_collection.get()
            if existing["ids"]:
                self.cv_collection.delete(ids=existing["ids"])
        
        if not chunks:
            return
        
        ids = [c["id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        metadatas = [c.get("metadata", {}) for c in chunks]
        embeddings = self._embed(texts)
        
        self.cv_collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        print(f"Added {len(chunks)} CV chunks to vector store")
    
    def add_job_description(self, job_id: str, description: str, metadata: Dict = None):
        """Add a job description to the store for future reference"""
        embedding = self._embed([description])[0]
        
        self.jobs_collection.upsert(
            ids=[job_id],
            documents=[description],
            metadatas=[metadata or {}],
            embeddings=[embedding]
        )
    
    def query_cv(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Query CV chunks relevant to a job description or requirement.
        
        Args:
            query: The job description or specific requirement
            n_results: Number of results to return
            
        Returns:
            List of relevant CV chunks with scores
        """
        query_embedding = self._embed([query])[0]
        
        results = self.cv_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        chunks = []
        for i, doc in enumerate(results["documents"][0]):
            chunks.append({
                "text": doc,
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i]
            })
        
        return chunks
    
    def find_similar_jobs(self, description: str, n_results: int = 3) -> List[Dict]:
        """Find similar jobs from history"""
        query_embedding = self._embed([description])[0]
        
        results = self.jobs_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        jobs = []
        for i, doc in enumerate(results["documents"][0]):
            jobs.append({
                "description": doc,
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i]
            })
        
        return jobs
    
    def get_cv_context(self, job_description: str, max_tokens: int = 2000) -> str:
        """
        Get relevant CV context for cover letter generation.
        Returns concatenated CV chunks relevant to the job.
        """
        chunks = self.query_cv(job_description, n_results=8)
        
        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough token-to-char ratio
        
        for chunk in chunks:
            if total_chars + len(chunk["text"]) > char_limit:
                break
            context_parts.append(chunk["text"])
            total_chars += len(chunk["text"])
        
        return "\n\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, int]:
        """Get collection statistics"""
        return {
            "cv_chunks": self.cv_collection.count(),
            "job_descriptions": self.jobs_collection.count()
        }


if __name__ == "__main__":
    # Test vector store
    store = JobVectorStore()
    print("Vector store initialized")
    print(f"Stats: {store.get_stats()}")
