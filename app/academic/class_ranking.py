"""OCR-assisted class score extraction and deterministic annual ranking."""
from __future__ import annotations

import io
import re
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from PIL import Image

from .schemas import ClassScoreSheet

_OCR = None
STUDENT_ID = re.compile(r'(?<!\d)(\d{8,20})(?!\d)')
NUMBER = re.compile(r'(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])')
YEAR_TERM = re.compile(r'(20\d{2})\s*[-—]\s*(20\d{2})\s*[-—]\s*([123])')


def engine():
    global _OCR
    if _OCR is None:
        from rapidocr import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def clean_text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def box_center(box):
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return sum(xs) / len(xs), sum(ys) / len(ys), max(ys) - min(ys)


def group_rows(tokens):
    heights = [token['height'] for token in tokens if token['height'] > 0]
    tolerance = max(8.0, median(heights) * 0.65 if heights else 12.0)
    rows = []
    for token in sorted(tokens, key=lambda item: (item['y'], item['x'])):
        row = next((candidate for candidate in reversed(rows) if abs(candidate['y'] - token['y']) <= tolerance), None)
        if row is None:
            row = {'y': token['y'], 'tokens': []}
            rows.append(row)
        row['tokens'].append(token)
        row['y'] = sum(item['y'] for item in row['tokens']) / len(row['tokens'])
    return [sorted(row['tokens'], key=lambda item: item['x']) for row in rows]


def parse_number(value):
    value = value.replace('O', '0').replace('o', '0').replace('，', '.').replace(',', '.')
    try:
        return float(value)
    except ValueError:
        return None


def parse_row(tokens):
    combined = ' '.join(clean_text(token['text']) for token in tokens)
    match = STUDENT_ID.search(combined)
    if not match:
        return None
    student_id = match.group(1)
    tail = combined[match.end():].strip(' |')
    number_matches = list(NUMBER.finditer(tail))
    if len(number_matches) < 3:
        return None
    name = tail[:number_matches[0].start()].strip(' |')
    if not name or name in ('姓名', '学号'):
        return None
    values = [parse_number(item.group()) for item in number_matches]
    values = [value for value in values if value is not None]
    if len(values) < 3:
        return None
    reported_average, reported_total, reported_rank = values[-3:]
    scores = values[:-3]
    confidence = round(sum(token['score'] for token in tokens) / len(tokens), 4)
    return {
        'student_id': student_id,
        'name': name,
        'scores': scores,
        'reported_average': reported_average,
        'reported_total': reported_total,
        'reported_rank': int(reported_rank) if reported_rank >= 1 else None,
        'ocr_confidence': confidence,
    }


def parse_score_image(filename, data, academic_year=None, term=None, class_name=None):
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        if width * height > 40_000_000:
            raise ValueError('图片像素过大')

    result = engine()(data)
    texts = list(result.txts or ())
    boxes = list(result.boxes or ())
    scores = list(result.scores or ())
    tokens = []
    for text, box, score in zip(texts, boxes, scores):
        x, y, box_height = box_center(box)
        tokens.append({'text': text, 'x': x, 'y': y, 'height': box_height, 'score': float(score)})
    all_text = filename + '\n' + '\n'.join(texts)
    year_match = YEAR_TERM.search(all_text)
    detected_year = f'{year_match[1]}-{year_match[2]}' if year_match else academic_year
    detected_term = int(year_match[3]) if year_match else term
    title = next((clean_text(text) for text in texts if YEAR_TERM.search(text)), '')
    detected_class = re.sub(r'[（(].*$', '', title).strip() or class_name
    if not detected_year or not detected_term or not detected_class:
        raise ValueError('未识别出学年、学期或班级，请在上传时填写')

    students, warnings, seen = [], [], set()
    for row_tokens in group_rows(tokens):
        student = parse_row(row_tokens)
        if not student:
            continue
        if student['student_id'] in seen:
            warnings.append(f"{student['student_id']} 在同一成绩单中重复，已保留第一条")
            continue
        seen.add(student['student_id'])
        if student['scores']:
            calculated_total = sum(student['scores'])
            calculated_average = calculated_total / len(student['scores'])
            if abs(calculated_total - student['reported_total']) > 0.6 or abs(calculated_average - student['reported_average']) > 0.15:
                warnings.append(f"{student['student_id']} {student['name']} 的识别分数与表内总分/平均分不一致，请核对")
        else:
            warnings.append(f"{student['student_id']} {student['name']} 未识别到课程分数，将使用表内平均分")
        if student['ocr_confidence'] < 0.85:
            warnings.append(f"{student['student_id']} {student['name']} OCR 置信度较低，请核对")
        students.append(student)
    if not students:
        warnings.append('未自动识别到学生数据，请人工补录或上传更清晰的原图')
    return ClassScoreSheet(
        academic_year=detected_year,
        term=detected_term,
        class_name=detected_class,
        source_name=filename,
        students=students,
        warnings=warnings,
    ).model_dump()


def annual_ranking(sheets):
    if len({(sheet['academic_year'], sheet['class_name']) for sheet in sheets}) != 1:
        raise ValueError('所有成绩单必须属于同一学年和班级')
    terms = sorted({sheet['term'] for sheet in sheets})
    merged = {}
    for sheet in sheets:
        for student in sheet['students']:
            record = merged.setdefault(student['student_id'], {'student_id': student['student_id'], 'name': student['name'], 'terms': {}, 'warnings': []})
            if record['name'] != student['name']:
                record['warnings'].append(f"姓名不一致：{record['name']} / {student['name']}")
            scores = student.get('scores') or []
            if scores:
                total, count = sum(scores), len(scores)
            elif student.get('reported_average') is not None:
                count = max(1, len(sheet.get('course_names') or []))
                total = student['reported_average'] * count
            else:
                total, count = 0, 0
            record['terms'][str(sheet['term'])] = {'total': total, 'course_count': count, 'average': total / count if count else None}
    rows = []
    for record in merged.values():
        missing_terms = [term for term in terms if str(term) not in record['terms'] or record['terms'][str(term)]['course_count'] == 0]
        total = sum(item['total'] for item in record['terms'].values())
        count = sum(item['course_count'] for item in record['terms'].values())
        average = float((Decimal(str(total)) / Decimal(count)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if count else None
        rows.append({**record, 'total_score': round(total, 2), 'course_count': count, 'annual_average': average,
                     'complete': not missing_terms, 'missing_terms': missing_terms, 'rank': None, 'rank_ratio': None})
    ranked = sorted((row for row in rows if row['complete'] and row['annual_average'] is not None), key=lambda row: (-row['annual_average'], -row['total_score'], row['student_id']))
    previous_average, previous_rank = None, 0
    for index, row in enumerate(ranked, 1):
        if previous_average is None or row['annual_average'] != previous_average:
            previous_rank = index
            previous_average = row['annual_average']
        row['rank'] = previous_rank
        row['rank_ratio'] = round(previous_rank / len(ranked), 6)
    return {'academic_year': sheets[0]['academic_year'], 'class_name': sheets[0]['class_name'], 'terms': terms,
            'student_count': len(rows), 'ranked_count': len(ranked),
            'rows': sorted(rows, key=lambda row: (row['rank'] is None, row['rank'] or 10**9, row['student_id']))}
