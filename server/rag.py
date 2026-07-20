# Логика парсинга pdf файлов в текст, разделения на чанки и эмбеддинга
# Выбран именно этот эмбеддер, т.к. он весит немного и обрабатывает русский язык

from pathlib import Path
import logging
import os
import uuid

import pymupdf
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)
from hashlib import sha1
BATCH_SIZE = 512

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
COLLECTION_NAME = "documents"

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST", "qdrant"),
    port=int(os.getenv("QDRANT_PORT", 6333)),
)

embedding_model = TextEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    cache_dir="models",
)


def embed(text: str) -> list[float]:
    return list(next(embedding_model.embed([text])))



def is_noise(text: str) -> bool:

    text = text.lower()

    if "содержание" in text:
        return True

    if "оглавление" in text:
        return True

    if "список литературы" in text:
        return True

    if "литература" == text.strip():
        return True

    return False

def init_collection():

    vector_size = len(embed("Hello"))


    if qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )


def split_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[str]:

    paragraphs = [
        p.strip()
        for p in text.split("\n\n")
        if p.strip()
    ]

    chunks = []
    current = ""

    for paragraph in paragraphs:
        if (is_noise(paragraph)): continue

        while len(paragraph) > chunk_size:

            chunks.append(paragraph[:chunk_size])

            paragraph = paragraph[chunk_size - overlap:]

        if len(current) + len(paragraph) + 2 <= chunk_size:

            if current:
                current += "\n\n"

            current += paragraph

        else:

            if current:
                chunks.append(current)

            current = paragraph

    if current:
        chunks.append(current)

    return chunks




def read_pdf(path: Path) -> list[str]:

    document = pymupdf.open(path)

    return [
        page.get_text()
        for page in document
    ]




def make_point_id(
    file: str,
    page: int,
    chunk: int,
) -> str:
    return sha1(
        f"{file}:{page}:{chunk}".encode()
    ).hexdigest()


def index_document(path: Path):

    logger.info("Indexing %s", path.name)

    if path.suffix.lower() == ".pdf":
        pages = read_pdf(path)


    else:
        raise ValueError(f"Unsupported document type: {path}")

    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="file",
                    match=MatchValue(value=path.name),
                )
            ]
        ),
    )

    chunks = []

    for page_number, text in enumerate(pages):

        if not text.strip():
            continue

        for chunk_number, chunk in enumerate(split_text(text)):

            chunks.append(
                {
                    "page": page_number + 1,
                    "chunk": chunk_number,
                    "text": chunk,
                }
            )

    if not chunks:
        return

    logger.info(
        "Embedding %d chunks...",
        len(chunks),
    )

    vectors = list(
        embedding_model.embed(
            [chunk["text"] for chunk in chunks]
        )
    )

    logger.info("Uploading to Qdrant...")

    points = []

    for chunk, vector in zip(chunks, vectors):

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector.tolist(),
                payload={
                    "file": path.name,
                    "page": chunk["page"],
                    "chunk": chunk["chunk"],
                    "text": chunk["text"],
                },
            )
        )

    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
    )

    logger.info(
        "Uploaded %d chunks from %s",
        len(points),
        path.name,
    )


def index_directory(directory: Path):

    init_collection()

    for path in directory.rglob("*"):

        if path.suffix.lower() in {
            ".pdf",
        }:

            index_document(path)


def search(
    query: str,
    limit: int = 5,
    score_threshold: float = 0.55,
) -> list[dict]:

    vector = embed(query)

    result = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit,
    )

    return [
        {
            "score": point.score,
            **point.payload,
        }
        for point in result.points
        if point.score >= score_threshold
    ]