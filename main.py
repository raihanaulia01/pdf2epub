from pypdf import PdfReader
import ColorPrint as cprint

reader = PdfReader("test_pdf/Gunatsu Volume 1.pdf")

print(len(reader.pages))