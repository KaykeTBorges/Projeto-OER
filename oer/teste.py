from pathlib import Path

from .pdf_reader import PDFReader


reader = PDFReader()

paper = reader.extract(
    Path("a.pdf")
)

print()

print("TITLE:")
print(paper["title"])

print()

print("DOI:")
print(paper["doi"])

print()

print("ABSTRACT:")
print(paper["abstract"][:1000])