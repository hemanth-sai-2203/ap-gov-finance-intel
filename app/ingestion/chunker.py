from typing import List, Dict, Any

def create_structured_chunks(
    pages_data: List[Dict[str, Any]],
    chunk_size: int = 400,
    overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Creates structured chunks from document pages while preserving page_number metadata.
    Splits text on paragraph boundaries or sentences to maintain structural semantics.
    """
    chunks = []
    
    for page in pages_data:
        page_num = page["page_number"]
        text = page["text"].strip()
        
        if not text:
            continue
            
        paragraphs = text.split("\n\n")
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append({
                        "page_number": page_num,
                        "text": current_chunk
                    })
                current_chunk = para
                
        if current_chunk:
            chunks.append({
                "page_number": page_num,
                "text": current_chunk
            })
            
    return chunks
