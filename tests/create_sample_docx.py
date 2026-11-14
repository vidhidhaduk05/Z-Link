"""
Generate a test docx manuscript with numbered citations and real biomedical references.
"""
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def add_superscript_run(paragraph, text):
    run = paragraph.add_run(text)
    rPr = run._r.get_or_add_rPr()
    va = OxmlElement('w:vertAlign')
    va.set(qn('w:val'), 'superscript')
    rPr.append(va)
    return run

def create_sample_manuscript(filename: str = "sample_radiology_manuscript.docx"):
    doc = docx.Document()
    
    # Title & Front Matter
    doc.add_heading("Deep Learning Diagnostic Evaluation in Pulmonary Imaging", level=1)
    doc.add_paragraph("Jane Doe, MD1; John Smith, PhD2; Alice Johnson, MD1")
    doc.add_paragraph("Department of Radiology, Academic Medical Center. Corresponding author: jdoe@example.org")
    
    # Abstract
    doc.add_heading("ABSTRACT", level=2)
    p_abs = doc.add_paragraph("Automated feature extraction and multi-reader validation are critical for reproducible medical imaging analysis (1, 2). Here we benchmark deep convolutional representations against multi-center clinical cohorts.")

    # Introduction
    doc.add_heading("INTRODUCTION", level=2)
    p_intro = doc.add_paragraph("Clinical image interpretation has increasingly integrated algorithmic feature quantification to reduce inter-observer variability (1). Modern computational frameworks allow large-scale multidimensional matrix evaluations across clinical cohorts (2, 3).")
    
    # Methods
    doc.add_heading("METHODS", level=2)
    p_meth = doc.add_paragraph("Array computations were processed using high-performance vector operations (1). Multi-reader adjudication was performed following standardized diagnostic criteria. Initial patient stratification protocols were adapted from established viral diagnostic studies (2). Model architectures were refined using automated neural network tuning.")
    # Add superscript citation
    p_meth2 = doc.add_paragraph("Statistical hypothesis testing was conducted with a two-tailed alpha of 0.05. Previous studies reported sensitivity gains of up to 14%")
    add_superscript_run(p_meth2, "3")
    p_meth2.add_run(". We also evaluated historical benchmark datasets")
    add_superscript_run(p_meth2, "4,5")
    p_meth2.add_run(" across three academic imaging centers.")

    # Results
    doc.add_heading("RESULTS", level=2)
    p_res = doc.add_paragraph("The overall sensitivity reached 94.2% (95% CI: 91.5-96.1%). Model performance remained consistent across internal and external validation splits (1, 3).")

    # References
    doc.add_heading("REFERENCES", level=2)
    doc.add_paragraph("1. Harris CR, Millman KJ, van der Walt SJ, et al. Array programming with NumPy. Nature. 2020;585(7825):357-362. doi: 10.1038/s41586-020-2649-2")
    doc.add_paragraph("2. Guan WJ, Ni ZY, Hu Y, et al. Clinical Characteristics of Coronavirus Disease 2019 in China. N Engl J Med. 2020;382(18):1708-1720. doi: 10.1056/NEJMoa2002032")
    doc.add_paragraph("3. McKinney SM, Sieniek M, Godbole V, et al. International evaluation of an AI system for breast cancer screening. Nature. 2020;577(7788):89-94. doi: 10.1038/s41586-019-1799-6")
    doc.add_paragraph("4. Fictitious Author, Broken Journal. Phantom study with invalid DOI. Phantom Radiol. 2022;1(1):10-15. doi: 10.1148/broken.invalid.doi.99999")
    doc.add_paragraph("5. Topol EJ. High-performance medicine: the convergence of human and artificial intelligence. Nat Med. 2019;25(1):44-56. doi: 10.1038/s41591-018-0300-7")

    doc.save(filename)
    print(f"Sample manuscript saved to {filename}")

if __name__ == "__main__":
    create_sample_manuscript()
