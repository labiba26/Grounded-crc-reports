"""Build gold-label sheets v2 (4 Oct 2026): one sheet, two-tumour columns, 'cannot find' rule.
Usage: python3 make_gold_sheets_v2.py  -> gold_labels_A.xlsx, gold_labels_B.xlsx
Old sheets must first be moved to _old_sheets/. Prefill: A only, from _old_sheets/gold_labels_A.xlsx."""
import openpyxl, os, sys, glob, warnings
warnings.filterwarnings("ignore")
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
OLD = openpyxl.load_workbook('_old_sheets/gold_labels_B.xlsx')
lists = OLD['Lists']
LST = {lists.cell(1,c).value:[lists.cell(r,c).value for r in range(2,13) if lists.cell(r,c).value] for c in range(1,11)}
for k in ('histologic_type','grade','pt','pn','node_status','lvi','margins'):
    LST[k] = [v for v in LST[k] if v != 'form: answer unreadable'] + ['unreadable in the scan']
LST['site'] = LST['site']
LST['ntum'] = ['1','2','3']
cases = [(r[0], r[1]) for r in OLD['Labels'].iter_rows(min_row=4, max_row=53, values_only=True)]
pdfs = {os.path.basename(p)[:3]: os.path.basename(p) for p in glob.glob('reports_pdf/G*.pdf')}
parts = {}
for p in sorted(glob.glob('reports_pdf/G*.pdf')): parts.setdefault(os.path.basename(p)[:3], []).append(os.path.basename(p))

GUIDE = open('GUIDE_v2.txt').read().split('\n')
CHEAT = [r[0] for r in OLD['Cheat sheet'].iter_rows(values_only=True)]
CHEAT = [c.replace('"form: answer unreadable"','"unreadable in the scan"') if c else c for c in CHEAT]

# columns: (header, listkey or None, width)
COLS = [
 ('Gold ID',None,8),('Case',None,15),('Report (PDF)',None,24),
 ('How many tumours?','ntum',10),
 ('T1 type','histologic_type',30),('T1 mucinous % (number, if given)','pct',11),('T1 grade','grade',16),('T1 pT','pt',14),('T1 site','site',15),
 ('T2 type (only if 2+ tumours)','histologic_type',30),('T2 grade','grade',16),('T2 pT','pt',14),('T2 site','site',15),
 ('pN (whole case)','pn',12),('Nodes positive (n)','n',10),('Nodes examined (n)','n',10),('Node status','node_status',14),
 ('Lymphovascular invasion','lvi',16),('Margins','margins',14),('Post-treatment (ypTNM)','post_treatment',12),
 ('Confidence','confidence',11),('Notes',None,60)]
YEL = PatternFill('solid', fgColor='FFF2A8'); GREY = PatternFill('solid', fgColor='E7E6E6'); BLUE = PatternFill('solid', fgColor='DDEBF7'); ORG = PatternFill('solid', fgColor='FCE4D6')

def build(name, who, prefill):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Labels'
    ws['A1'] = 'Annotator:'; ws['B1'] = who; ws['C1'] = 'Date:'
    ws['F1'] = 'Fill EVERY yellow cell in T1 and the whole-case columns. Blank = forgot. Cannot find it -> "not stated". Tab "Guide" has the rules.'
    ws['A1'].font = ws['C1'].font = Font(bold=True)
    for c,(h,k,w) in enumerate(COLS,1):
        cell = ws.cell(2,c,h); cell.font = Font(bold=True); cell.alignment = Alignment(wrap_text=True, vertical='top')
        cell.fill = BLUE if h.startswith('T1') else ORG if h.startswith('T2') else GREY
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
    ex = ['EXAMPLE','(invented)','—','2','adenocarcinoma NOS',None,'G2','pT3','sigmoid','adenocarcinoma NOS','G1','pT1','transverse','pN1',2,17,'positive','present','clear','no','sure','Invented. Two tumours: sigmoid pT3 G2 = index (highest pT); transverse pT1 G1. Nodes 2/17 for the whole case.']
    for c,v in enumerate(ex,1): ws.cell(3,c,v).fill = GREY
    for i,(gid,case) in enumerate(cases):
        r = 4+i
        ws.cell(r,1,gid); ws.cell(r,2,case)
        fl = parts.get(gid, [f'{gid}_{case}.pdf'])
        ws.cell(r,3,fl[0] if len(fl)==1 else ' + '.join(fl))
        ws.cell(r,3).hyperlink = 'reports_pdf/'+fl[0]; ws.cell(r,3).font = Font(color='0563C1', underline='single')
        for c in range(4,len(COLS)+1): ws.cell(r,c).fill = YEL
        if prefill and gid in prefill:
            for c,v in prefill[gid].items(): ws.cell(r,c,v)
    ws.freeze_panes = 'D4'
    # Lists
    ls = wb.create_sheet('Lists'); col = {}
    for j,(k,v) in enumerate(LST.items(),1):
        ls.cell(1,j,k)
        for i,x in enumerate(v,2): ls.cell(i,j,x)
        col[k] = (j, len(v)+1)
    for c,(h,k,w) in enumerate(COLS,1):
        L = openpyxl.utils.get_column_letter(c); rng = f'{L}4:{L}53'
        if k in col:
            j,n = col[k]; dv = DataValidation(type='list', formula1=f"Lists!${openpyxl.utils.get_column_letter(j)}$2:${openpyxl.utils.get_column_letter(j)}${n}", allow_blank=True, showErrorMessage=True, errorTitle='Use the list', error='Pick from the drop-down.')
        elif k == 'pct': dv = DataValidation(type='whole', operator='between', formula1='0', formula2='100', allow_blank=True, showErrorMessage=True, error='Whole number 0-100, or blank.')
        elif k == 'n': dv = DataValidation(type='whole', operator='between', formula1='0', formula2='200', allow_blank=True, showErrorMessage=True, error='Whole number, or blank.')
        else: continue
        ws.add_data_validation(dv); dv.add(rng)
    g = wb.create_sheet('Guide', 0)
    for i,t in enumerate(GUIDE,1): g.cell(i,1,t)
    g.column_dimensions['A'].width = 130
    ch = wb.create_sheet('Cheat sheet', 2)
    for i,t in enumerate(CHEAT,1): ch.cell(i,1,t)
    ch.column_dimensions['A'].width = 130
    wb.active = 1
    wb.save(name)

prefill = None
if '--prefill' in sys.argv:
    o = openpyxl.load_workbook('_old_sheets/gold_labels_A.xlsx')['Labels']
    # old cols: D type,E %,F grade,G pT,H pN,I npos,J nexam,K nodestat,L lvi,M margins,N site,O post,P conf,Q notes
    prefill = {}
    for row in o.iter_rows(min_row=4, max_row=53):
        gid = row[0].value; d = {}
        for oc,nc in [(4,5),(5,6),(6,7),(7,8),(8,14),(9,15),(10,16),(11,17),(12,18),(13,19),(14,9),(15,20),(16,21),(17,22)]:
            v = row[oc-1].value
            if v is not None:
                v = 'unreadable in the scan' if v == 'form: answer unreadable' else v
                d[nc] = v
        if d: prefill[gid] = d
    print('prefilled rows:', len(prefill))
build('gold_labels_A.xlsx','Labiba',prefill)
build('gold_labels_B.xlsx',None,None)
