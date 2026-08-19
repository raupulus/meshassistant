import unittest
import io
import tarfile
import gzip
from Models.Aemet import Aemet, get_province_emma_info, PROV_EMMA_MAP
from Models.Database import Database
from cron_tasks import extract_xmls_from_bytes, _filter_alert_xml_for_province


class TestAemetAlerts(unittest.TestCase):

    def test_emma_mapping_andalucia(self):
        andalucia_provinces = ["Almeria", "Cadiz", "Cordoba", "Granada", "Huelva", "Jaen", "Malaga", "Sevilla"]
        for prov in andalucia_provinces:
            info = get_province_emma_info(prov)
            self.assertIsNotNone(info, f"Mapping failed for {prov}")
            self.assertEqual(info["ccaa_code"], "61", f"CCAA code should be 61 for {prov}")
            self.assertEqual(len(info["emma_prefix"]), 4, f"EMMA prefix should be 4 digits for {prov}")
            self.assertTrue(info["emma_prefix"].startswith("61"))

    def test_emma_mapping_cadiz(self):
        info = get_province_emma_info("Cadiz")
        self.assertIsNotNone(info)
        self.assertEqual(info["prov_code"], "11")
        self.assertEqual(info["ccaa_code"], "61")
        self.assertEqual(info["emma_prefix"], "6111")
        self.assertIn("GRAZALEMA", info["aliases"])
        self.assertIn("LITORAL GADITANO", info["aliases"])

    def test_extract_xmls_plain(self):
        xml_data = b'<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>123</identifier></alert>'
        results = extract_xmls_from_bytes(xml_data)
        self.assertEqual(len(results), 1)
        self.assertIn("<identifier>123</identifier>", results[0])

    def test_extract_xmls_tar_and_gz(self):
        xml1 = b'<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>file1</identifier></alert>'
        xml2 = b'<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>file2</identifier></alert>'

        gz_data = gzip.compress(xml2)

        bio = io.BytesIO()
        with tarfile.open(fileobj=bio, mode='w') as tar:
            t1 = tarfile.TarInfo(name='alert1.xml')
            t1.size = len(xml1)
            tar.addfile(t1, io.BytesIO(xml1))

            t2 = tarfile.TarInfo(name='alert2.xml.gz')
            t2.size = len(gz_data)
            tar.addfile(t2, io.BytesIO(gz_data))

        tar_bytes = bio.getvalue()
        results = extract_xmls_from_bytes(tar_bytes)
        self.assertEqual(len(results), 2)
        self.assertTrue(any('file1' in r for r in results))
        self.assertTrue(any('file2' in r for r in results))

    def test_parse_cap_es_discard_green(self):
        db = Database()
        green_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <info>
            <language>es-ES</language>
            <event>Aviso de nevadas de nivel verde</event>
            <area><areaDesc>Campiña gaditana</areaDesc></area>
            <parameter><valueName>nivel</valueName><value>verde</value></parameter>
          </info>
        </alert>'''
        alert_text, pub_text = db._parse_cap_es(green_xml)
        self.assertIsNone(alert_text, "Nivel verde should be discarded")
        self.assertIsNone(pub_text, "Nivel verde should be discarded")

    def test_parse_cap_es_yellow(self):
        db = Database()
        yellow_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <info>
            <language>es-ES</language>
            <event>Aviso de vientos</event>
            <headline>Viento racheado fuerte</headline>
            <description>Rachas de hasta 80 km/h</description>
            <area><areaDesc>Litoral gaditano</areaDesc></area>
            <parameter><valueName>nivel</valueName><value>amarillo</value></parameter>
          </info>
        </alert>'''
        alert_text, pub_text = db._parse_cap_es(yellow_xml)
        self.assertIsNotNone(alert_text)
        self.assertIsNotNone(pub_text)
        self.assertIn("amarillo", pub_text)
        self.assertIn("Litoral gaditano", pub_text)

    def test_filter_alert_xml_cadiz(self):
        emma_cadiz = get_province_emma_info("Cadiz")

        cadiz_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <info>
            <event>Aviso de tormentas</event>
            <area>
              <areaDesc>Grazalema</areaDesc>
              <geocode><valueName>EMMA_ID</valueName><value>611104</value></geocode>
            </area>
          </info>
        </alert>'''

        almeria_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <info>
            <event>Aviso de temperaturas máximas</event>
            <area>
              <areaDesc>Valle del Almanzora y Los Vélez</areaDesc>
              <geocode><valueName>EMMA_ID</valueName><value>610401</value></geocode>
            </area>
          </info>
        </alert>'''

        self.assertTrue(_filter_alert_xml_for_province(cadiz_xml, emma_cadiz, "Cadiz"))
        self.assertFalse(_filter_alert_xml_for_province(almeria_xml, emma_cadiz, "Cadiz"))


if __name__ == '__main__':
    unittest.main()
