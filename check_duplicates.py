from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel
from sqlalchemy import func

session = SessionLocal()
total_chunks = session.query(DocumentChunkModel).count()
total_docs = session.query(DocumentModel).count()

# Distinct documents by title + financial_year
unique_docs_count = session.query(func.count(func.distinct(DocumentModel.title + DocumentModel.financial_year))).scalar()

doc_dups = (
    session.query(DocumentModel.title, DocumentModel.financial_year, func.count(DocumentModel.id))
    .group_by(DocumentModel.title, DocumentModel.financial_year)
    .having(func.count(DocumentModel.id) > 1)
    .order_by(func.count(DocumentModel.id).desc())
    .all()
)

print(f"TOTAL_DOCUMENTS_IN_DB: {total_docs}")
print(f"UNIQUE_DOCUMENTS_ACTUAL: {unique_docs_count}")
print(f"TOTAL_CHUNKS_IN_DB: {total_chunks}")
print(f"DOCUMENTS_WITH_DUPLICATES: {len(doc_dups)}")
print()
print("Top Duplicated Documents in DB:")
for title, yr, cnt in doc_dups[:12]:
    clean_title = " ".join(title.split())
    print(f"  - [{cnt} copies] ({yr}) {clean_title[:55]}")

session.close()
