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
            
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=1500
        )
        self.prompt = PromptTemplate(
            input_variables=["cv_context","company","job_title","location","job_description","requirements"],
            template="""Write a compelling cover letter.

CANDIDATE CV CONTEXT: {cv_context}
COMPANY: {company}
ROLE: {job_title}
LOCATION: {location}
JOB DESCRIPTION: {job_description}
REQUIREMENTS: {requirements}

Write the cover letter now:"""
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
