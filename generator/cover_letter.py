import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

class CoverLetterGenerator:
    def __init__(self, vectorstore=None):
        self.vectorstore = vectorstore
        self.llm = ChatOpenAI(
            base_url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model="deepseek-chat",
            temperature=0.7,
            max_tokens=1500
        )
        self.prompt = PromptTemplate(
            input_variables=["cv_context","company","job_title","location","job_description","requirements"],
            template="""You are writing a cover letter for Pavol Just, an AI engineer based in Trenčín, Slovakia targeting DACH and CEE roles.

Key facts about Pavol:
- 3+ years building production ML systems, RAG pipelines, and autonomous agent architectures
- MalVision (2023): host-based ransomware detection, behavioral ML scoring, MLflow tracking, FastAPI, Docker
- BTC/MSTR Correlation Trader (2023, rebuilt 2025): live quantitative trading system, ensemble ML models, Alpaca API, IBKR execution, Streamlit dashboard
- ops-pilot-ai (2024): FastAPI + LangChain + ChromaDB RAG service, deployed on Google Cloud Run, GitHub Actions CI/CD
- LLM-Guard (2024-2025): real-time LLM agent security, 85.7% detection rate across 6 MITRE ATT&CK techniques, OWASP LLM Top 10 coverage, Splunk integration
- job-hunter (2025-2026): autonomous job application agent, Telegram approval flow, RAG-backed cover letter generation
- MA International Relations (Anglia Ruskin), ML Certificate (Gateshead College)
- Available immediately, open to relocation, fluent English/Slovak/Czech, intermediate German

CV CONTEXT (from RAG): {cv_context}
COMPANY: {company}
ROLE: {job_title}
LOCATION: {location}
JOB DESCRIPTION: {job_description}
REQUIREMENTS: {requirements}

Write a 3-paragraph cover letter. Reference at least one specific project by name that is relevant to this role. Be direct and specific. Close with a concrete ask. Do not use generic phrases like 'I am excited to apply'."""
        )
        self.provider = "deepseek"
        self.chain = self.prompt | self.llm

    def generate(self, job_title, company, job_description, location="", requirements="", additional_context=""):
        cv_context = additional_context or "No CV context available"
        if self.vectorstore:
            cv_context = self.vectorstore.get_cv_context(f"{job_title} {company}", max_tokens=2000)
        result = self.chain.invoke({
            "cv_context": cv_context,
            "company": company,
            "job_title": job_title,
            "location": location,
            "job_description": job_description[:3000],
            "requirements": requirements[:1000]
        })
        return {"cover_letter": result.content.strip(), "provider": "deepseek"}

    def generate_from_job(self, job):
        return self.generate(
            job_title=job.get("title",""),
            company=job.get("company",""),
            job_description=job.get("description",""),
            location=job.get("location",""),
            requirements=job.get("requirements","")
        )

def create_generator(vectorstore=None):
    return CoverLetterGenerator(vectorstore=vectorstore)
