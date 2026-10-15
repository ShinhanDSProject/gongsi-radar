"""원문 파서와 문단 정렬. 실행: python -m unittest -v  (pytest로도 실행 가능)"""
import io
import unittest
import zipfile

from radar.align import diff_documents, number_changes
from radar.config import ALIGN_THRESHOLDS, ROOT
from radar.embed import make_embedder
from radar.parser import ParseError, choose_main_file, decode, parse_filing_zip, repair

DATA = ROOT / "samples" / "data" / "filings"
OLD, NEW = "20250318000412", "20260317000388"


def load(rno):
    return parse_filing_zip((DATA / f"{rno}.zip").read_bytes(), rno)


class ParserTest(unittest.TestCase):
    def test_picks_main_file_not_audit_report(self):
        names = [f"{OLD}_00760.xml", f"{OLD}.xml", f"{OLD}_00761.xml"]
        self.assertEqual(choose_main_file(names, OLD), f"{OLD}.xml")
        with self.assertRaises(ParseError):
            choose_main_file([f"{OLD}_00760.xml"], OLD)

    def test_cp949_declared_as_utf8(self):
        doc = load(OLD)
        self.assertEqual(doc.encoding_declared, "utf-8")
        self.assertEqual(doc.encoding_used, "cp949")
        self.assertTrue(any("인코딩" in w for w in doc.warnings))

    def test_repairs_amp_fake_tags_and_cr(self):
        fixed, fixes = repair('<P>R&D와 M&A, <시장 동향> 참고&cr;끝 &amp; 유지</P>')
        self.assertEqual(fixes["amp"], 2)
        self.assertEqual(fixes["fake_tags"], 1)
        self.assertEqual(fixes["cr"], 1)
        self.assertIn("&amp; 유지", fixed)          # 이미 이스케이프된 &amp;는 그대로
        self.assertNotIn("&amp;amp;", fixed)

    def test_te_tu_cells_collected_and_strict_mode(self):
        doc = load(NEW)
        self.assertEqual(doc.mode, "strict")
        self.assertGreater(doc.cell_counts["TE"] + doc.cell_counts["TU"], 0)
        tbl = doc.tables("II-2")[0]
        self.assertEqual(tbl.unit, "(단위: 백만원)")
        self.assertEqual(tbl.rows[2], ["LFP 전구체", "24,000", "2.4%"])

    def test_fake_tag_text_kept(self):
        doc = load(NEW)
        self.assertTrue(any("<시장 동향>" in b.text for b in doc.paragraphs("II-7")))

    def test_paragraph_ids_are_content_hashes(self):
        o, n = load(OLD), load(NEW)
        same_o = [b.id.split(":")[-1] for b in o.paragraphs("I-1")]
        same_n = [b.id.split(":")[-1] for b in n.paragraphs("I-1")]
        self.assertEqual(same_o[0], same_n[0])  # 같은 문장 → 같은 해시
        self.assertTrue(all(b.id.startswith(NEW + ":") for b in n.blocks))

    def test_bad_zip_reports_error(self):
        with self.assertRaises(ParseError):
            parse_filing_zip('{"status":"014","message":"파일이 존재하지 않습니다"}'.encode(), OLD)

    def test_recover_mode_warns_instead_of_silent_loss(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("X.xml", '<DOCUMENT><BODY><SECTION-1><TITLE>I. 가</TITLE><P>정상 문단</P><P>닫히지 않은 문단'
                                '</SECTION-1></BODY></DOCUMENT>')
        doc = parse_filing_zip(buf.getvalue(), "X")
        self.assertEqual(doc.mode, "recover")
        self.assertTrue(any("복구 모드" in w for w in doc.warnings))

    def test_decode_utf8_bom(self):
        text, _, used, _ = decode("﻿<a/>".encode("utf-8"))
        self.assertEqual(used, "utf-8")
        self.assertEqual(text, "<a/>")


class AlignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.changes = diff_documents(load(OLD), load(NEW), make_embedder("tfidf"), ALIGN_THRESHOLDS["tfidf"])

    def find(self, needle, side="new"):
        for c in self.changes:
            if needle in (c.new_text if side == "new" else c.old_text):
                return c
        self.fail(f"변경을 찾지 못함: {needle}")

    def test_new_lawsuit_is_new(self):
        self.assertEqual(self.find("특허침해").edit_type, "신설")

    def test_numbers_only_change(self):
        c = self.find("655억원")
        self.assertEqual(c.edit_type, "수치 수정")
        self.assertEqual(number_changes(c.old_text, c.new_text), [{"old": "412억원", "new": "655억원"}])

    def test_year_rollover_alone_is_not_a_change(self):
        # '해당사항 없음'과 소송 외 문단 중 연도만 바뀐 문단은 변경 목록에 없어야 함
        self.assertNotIn("수치 수정", {c.edit_type for c in self.changes if "본점은" in c.new_text and "3개" not in c.new_text})

    def test_split_detected(self):
        c = self.find("70,000톤")
        self.assertIn("분할", c.flags)
        self.assertEqual(len(c.new), 2)

    def test_deleted_paragraph(self):
        self.assertEqual(self.find("베트남 법인", side="old").edit_type, "삭제")

    def test_same_slot_rewrite_paired(self):
        c = self.find("리튬·니켈 가격 하락에 따른 판매단가 인하")
        self.assertEqual(c.edit_type, "표현 수정")
        self.assertIn("같은 자리", c.flags)

    def test_korean_amounts_paired(self):
        self.assertIn({"old": "1조 2,840억원", "new": "1조 120억원"},
                      number_changes("2024년 매출액은 1조 2,840억원으로", "2025년 매출액은 1조 120억원으로"))

    def test_number_followed_by_hangul_is_not_a_number(self):
        self.assertEqual(number_changes("1심이 진행 중", "1심에서 판결"), [])


if __name__ == "__main__":
    unittest.main()
