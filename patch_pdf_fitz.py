import fitz
import os

pdf_path = "/Users/anubhav/Documents/EV_Tariff_Optimization/Google_Drive_Submission/EVTariffpresentation.pdf"
temp_pdf_path = "/Users/anubhav/Documents/EV_Tariff_Optimization/Google_Drive_Submission/EVTariffpresentation_fitz.pdf"

if not os.path.exists(pdf_path):
    print(f"Error: PDF not found at {pdf_path}")
    exit(1)

doc = fitz.open(pdf_path)
print(f"Opened PDF. Total pages: {len(doc)}")

for i, page in enumerate(doc):
    rect = page.rect
    w, h = rect.width, rect.height
    print(f"Page {i}: size {w}x{h}")
    
    # 1. Sample background color at bottom right corner (w-5, h-5)
    # Extract a 10x10 pixmap centered around (w-5, h-5)
    clip_rect = fitz.Rect(w - 10, h - 10, w, h)
    pix = page.get_pixmap(clip=clip_rect)
    
    # Get RGB of pixel (5, 5) in clip coordinates
    rgb = pix.pixel(5, 5)
    color = [c / 255.0 for c in rgb]  # PyMuPDF uses 0.0 to 1.0 floats
    print(f"  Sampled BG color: {rgb} -> {color}")
    
    # 2. Define watermark region proportionally
    # Based on original image dimensions 1376x768:
    # Watermark was from X = w_img - 240 to w_img - 10, Y = h_img - 50 to h_img - 10
    # Let's map X_pdf = X_img * (w / 1376), Y_pdf = Y_img * (h / 768)
    x_scale = w / 1376.0
    y_scale = h / 768.0
    
    x1 = (1376 - 240) * x_scale
    x2 = (1376 - 10) * x_scale
    y1 = (768 - 50) * y_scale
    y2 = (768 - 10) * y_scale
    
    watermark_rect = fitz.Rect(x1, y1, x2, y2)
    print(f"  Drawing patch rect: X: {x1:.2f} to {x2:.2f}, Y: {y1:.2f} to {y2:.2f}")
    
    # 3. Draw a solid matching rectangle directly over the watermark on the page
    # color: border color, fill_color: fill color, width: border width
    page.draw_rect(watermark_rect, color=color, fill=color, width=0)

# Save the patched PDF
doc.save(temp_pdf_path)
doc.close()
print(f"Patched PDF saved successfully to {temp_pdf_path}")

# Overwrite original
os.replace(temp_pdf_path, pdf_path)
print("Original PDF replaced with clean vector-patched version.")
