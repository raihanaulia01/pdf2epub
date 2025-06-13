import pymupdf
import json
doc = pymupdf.open("test_pdf/Gunatsu Volume 1.pdf")

for page_index in range(10): # iterate over pdf pages
    page = doc[page_index] # get the page
    image_list = page.get_images()

    # print the number of images found on the page
    if image_list:
        print(f"Found {len(image_list)} images on page {page_index}")
    else:
        print("No images found on page", page_index)

    for image_index, img in enumerate(image_list, start=1): # enumerate the image list
        xref = img[0] # get the XREF of the image
        print(img)
        pix = pymupdf.Pixmap(doc, xref)
        # pix.pil_tobytes

        if pix.n - pix.alpha > 3: # CMYK: convert to RGB first
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

        # pix.save("page_%s-image_%s.png" % (page_index, image_index)) # save the image as png
        pix = None

# print(doc.get_toc())
# for i in range(1):
#   for element in doc[i].get_text("dict")['blocks']:
#     if element["type"] == 1:
#       print(f"{element["number"]} \n {element}")

# print(doc[10].get_text("dict")['blocks'][2])