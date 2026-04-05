"""
CV Ingestion for RAG Pipeline
Chunks CV content for vector store retrieval
"""

import os
from pathlib import Path
from typing import List, Dict
import re
from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from PDF"""
    reader = PdfReader(pdf_path)
    text_parts = []
    
    for page in reader.pages:
        text_parts.append(page.extract_text())
    
    return "\n".join(text_parts)


def chunk_cv_by_section(cv_text: str) -> List[Dict[str, str]]:
    """
    Chunk CV into semantic sections for better retrieval.
    Preserves context by keeping related information together.
    """
    chunks = []
    
    # Common CV section headers - remove inline (?i) flags
    section_patterns = [
        r"(professional\s+summary|summary|profile|objective)",
        r"(work\s+experience|experience|employment|career\s+history)",
        r"(education|academic|qualifications)",
        r"(skills|technical\s+skills|competencies|technologies)",
        r"(certifications?|certificates?|credentials)",
        r"(projects?|portfolio|key\s+projects)",
        r"(languages?|language\s+skills)",
        r"(publications?|research|papers)",
        r"(awards?|achievements?|honors?)",
    ]
    
    # Split by section headers
    # Build combined pattern without inline flags
    combined_pattern = "|".join(f"({p})" for p in section_patterns)
    # Use flags parameter for case-insensitive matching
    sections = re.split(combined_pattern, cv_text, flags=re.IGNORECASE)
    
    current_section = "header"
    current_text = ""
    chunk_id = 0
    
    for part in sections:
        if not part or not part.strip():
            continue
        
        # Check if this is a section header
        is_header = False
        for pattern in section_patterns:
            # Use re.IGNORECASE flag in match
            if re.match(pattern, part.strip(), flags=re.IGNORECASE):
                # Save previous section
                if current_text.strip():
                    chunks.append({
                        "id": f"cv_{chunk_id}",
                        "text": current_text.strip(),
                        "metadata": {"section": current_section}
                    })
                    chunk_id += 1
                
                current_section = part.strip().lower()
                current_text = ""
                is_header = True
                break
        
        if not is_header:
            current_text += part
    
    # Don't forget the last section
    if current_text.strip():
        chunks.append({
            "id": f"cv_{chunk_id}",
            "text": current_text.strip(),
            "metadata": {"section": current_section}
        })
    
    # If no sections found, chunk by size
    if len(chunks) <= 1:
        chunks = chunk_by_size(cv_text, chunk_size=500, overlap=50)
    
    return chunks


def chunk_by_size(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, str]]:
    """Fallback: chunk by character count with overlap"""
    chunks = []
    words = text.split()
    
    chunk_id = 0
    i = 0
    
    while i < len(words):
        # Get chunk_size worth of words (rough approximation)
        chunk_words = words[i:i + chunk_size // 5]  # Avg 5 chars per word
        chunk_text = " ".join(chunk_words)
        
        chunks.append({
            "id": f"cv_{chunk_id}",
            "text": chunk_text,
            "metadata": {"section": "general", "chunk_index": chunk_id}
        })
        
        chunk_id += 1
        i += len(chunk_words) - (overlap // 5)  # Overlap
    
    return chunks


def add_skill_specific_chunks(chunks: List[Dict], cv_text: str) -> List[Dict]:
    """
    Add chunks specifically highlighting key skills for target roles.
    These are the skills that need to show up in cover letters.
    """
    # Key skills to extract explicitly
    skill_keywords = {
        "langchain": ["langchain", "lang chain", "retrieval qa", "llm chain"],
        "azure_openai": ["azure openai", "azure ai", "azure ml", "azure machine learning"],
        "rag": ["rag", "retrieval augmented", "vector store", "chromadb", "embeddings"],
        "mlflow": ["mlflow", "ml flow", "experiment tracking", "model registry"],
        "fastapi": ["fastapi", "fast api", "api development"],
        "docker": ["docker", "container", "kubernetes", "k8s"],
        "mlops": ["mlops", "ml ops", "ci/cd", "deployment"],
        "python": ["python", "pytorch", "tensorflow", "scikit"],
    }
    
    cv_lower = cv_text.lower()
    
    for skill_name, keywords in skill_keywords.items():
        for keyword in keywords:
            if keyword in cv_lower:
                # Find the sentence/paragraph containing this skill
                start = cv_lower.find(keyword)
                # Get surrounding context (500 chars each side)
                context_start = max(0, start - 250)
                context_end = min(len(cv_text), start + len(keyword) + 250)
                context = cv_text[context_start:context_end].strip()
                
                if context:
                    chunks.append({
                        "id": f"skill_{skill_name}",
                        "text": context,
                        "metadata": {
                            "section": "skills",
                            "skill": skill_name,
                            "priority": "high"
                        }
                    })
                break  # Only add once per skill category
    
    return chunks


def ingest_cv(cv_path: str, vectorstore) -> int:
    """
    Main ingestion function - reads CV and populates vector store.
    
    Args:
        cv_path: Path to CV PDF
        vectorstore: JobVectorStore instance
        
    Returns:
        Number of chunks added
    """
    # Extract text
    if cv_path.endswith('.pdf'):
        cv_text = extract_text_from_pdf(cv_path)
    else:
        with open(cv_path, 'r') as f:
            cv_text = f.read()
    
    print(f"Extracted {len(cv_text)} characters from CV")
    
    # Chunk by section
    chunks = chunk_cv_by_section(cv_text)
    print(f"Created {len(chunks)} section-based chunks")
    
    # Add skill-specific chunks
    chunks = add_skill_specific_chunks(chunks, cv_text)
    print(f"Total chunks after skill extraction: {len(chunks)}")
    
    # Add to vector store
    vectorstore.add_cv_chunks(chunks, clear_existing=True)
    
    return len(chunks)


if __name__ == "__main__":
    from vectorstore import JobVectorStore
    
    # Test ingestion
    cv_path = "./cv/cv_base.pdf"
    
    if Path(cv_path).exists():
        store = JobVectorStore()
        num_chunks = ingest_cv(cv_path, store)
        print(f"Ingested {num_chunks} chunks from CV")
    else:
        print(f"CV not found at {cv_path}")
        print("Place your CV at ./cv/cv_base.pdf and run again")
