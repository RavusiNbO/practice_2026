from pathlib import Path

from rag import index_directory

index_directory(
    Path("documents")
)