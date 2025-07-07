import fitz
import pikepdf
import pytesseract
from PIL import Image
import io
import re
from typing import Optional, List
from fastapi import UploadFile, HTTPException
from models import Customer

class PDFParser:
    def __init__(self):
        self.password_attempts = []
    
    def generate_password_candidates(self, customer: Customer) -> List[str]:
        candidates = []
        
        name_parts = customer.name.lower().split()
        phone = re.sub(r'[^\d]', '', customer.phone_number)
        dob = customer.date_of_birth
        
        dob_formats = [
            dob.replace('-', ''),
            dob.replace('/', ''),
            dob.replace('-', '')[-2:],
            dob.replace('/', '')[-2:],
        ]
        
        for name_part in name_parts:
            candidates.extend([
                name_part,
                name_part.capitalize(),
                name_part.upper(),
            ])
        
        candidates.extend([
            phone,
            phone[-4:],
            phone[-6:],
            phone[-8:],
        ])
        
        candidates.extend(dob_formats)
        
        for name_part in name_parts:
            for dob_format in dob_formats:
                candidates.extend([
                    f"{name_part}{dob_format}",
                    f"{name_part.capitalize()}{dob_format}",
                    f"{dob_format}{name_part}",
                ])
        
        for name_part in name_parts:
            candidates.extend([
                f"{name_part}{phone[-4:]}",
                f"{name_part.capitalize()}{phone[-4:]}",
                f"{phone[-4:]}{name_part}",
            ])
        
        return list(set(candidates))
    
    def try_password_protected_pdf(self, pdf_bytes: bytes, customer: Customer) -> Optional[str]:
        password_candidates = self.generate_password_candidates(customer)
        
        for password in password_candidates:
            try:
                with pikepdf.open(io.BytesIO(pdf_bytes), password=password) as pdf:
                    text_content = ""
                    for page in pdf.pages:
                        page_text = str(page)
                        text_content += page_text + "\n"
                    
                    if text_content.strip():
                        return text_content
            except pikepdf.PasswordError:
                continue
            except Exception as e:
                continue
        
        return None
    
    def extract_text_with_pymupdf(self, pdf_bytes: bytes) -> str:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_content = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_content += page.get_text() + "\n"
            
            doc.close()
            return text_content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")
    
    def extract_text_with_ocr(self, pdf_bytes: bytes) -> str:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_content = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                
                img = Image.open(io.BytesIO(img_data))
                
                ocr_text = pytesseract.image_to_string(img, config='--psm 6')
                text_content += ocr_text + "\n"
            
            doc.close()
            return text_content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to perform OCR on PDF: {str(e)}")
    
    async def parse_pdf(self, file: UploadFile, customer: Customer) -> str:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        content = await file.read()
        
        try:
            text_content = self.extract_text_with_pymupdf(content)
            
            if not text_content.strip():
                text_content = self.extract_text_with_ocr(content)
            
            return text_content
        
        except Exception as e:
            password_content = self.try_password_protected_pdf(content, customer)
            
            if password_content:
                return password_content
            
            try:
                text_content = self.extract_text_with_ocr(content)
                return text_content
            except Exception as ocr_error:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to parse PDF. Could not extract text or decrypt: {str(e)}"
                )
    
    def clean_extracted_text(self, text: str) -> str:
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line and len(line) > 2:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)