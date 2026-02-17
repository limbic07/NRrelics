from cnocr import CnOcr

img_fp = './temp.jpg'
ocr = CnOcr(det_model_name='naive_det') 
print('OCR初始化完成')
out = ocr.ocr(img_fp)

print(out)