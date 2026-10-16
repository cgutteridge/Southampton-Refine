"""University building register: normalise, lookups, footprint match, photo widths (no network, no gdal)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buildings as B  # noqa: E402

SQUARE = [[0, 0], [20, 0], [20, 20], [0, 20]]


def row(i, x, z, image='', rings=None):
    return {'id': i, 'label': f'Building {i}', 'lat': 0, 'lon': 0, 'x': x, 'z': z, 'in_map': True,
            'image': image, 'uri': '', 'rings': rings or []}


STORE = [row('2', 100, 100, 'https://d.example/image-archive/buildings/200/2.jpg', [SQUARE]),
         row('10', 500, 500), row('2A', 108, 104, '', [])]


class Lookups(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(B, 'load', return_value=STORE)
        p.start()
        self.addCleanup(p.stop)

    def test_cell_and_bbox_use_the_centre(self):
        self.assertEqual([b['id'] for b in B.in_bbox(90, 90, 110, 110)], ['2', '2A'])
        self.assertEqual([b['id'] for b in B.in_cell(3, 3)], ['10'])

    def test_building_is_case_insensitive_and_near_is_sorted(self):
        self.assertEqual([b['id'] for b in B.building('2a')], ['2A'])
        self.assertEqual([b['id'] for _d, b in B.near(101, 101, 30)], ['2', '2A'])

    def test_photo_widths_swap_the_folder(self):
        self.assertEqual(B.photos(STORE[0], 400), ['https://d.example/image-archive/buildings/400/2.jpg'])
        self.assertEqual(B.photos(STORE[1]), [])
        with self.assertRaises(ValueError):
            B.photos(STORE[0], 123)

    def test_describe_says_what_exists(self):
        self.assertIn('photo, outline', B.describe(STORE[0]))
        self.assertIn('no photo, no outline', B.describe(STORE[1]))


class Footprint(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(B, 'load', return_value=[dict(STORE[0], x=500, z=500), STORE[1], STORE[2]])
        p.start()
        self.addCleanup(p.stop)

    def test_register_centre_inside_the_osm_outline(self):
        osm = [[(95, 95), (115, 95), (115, 115), (95, 115)]]
        self.assertEqual([b['id'] for b in B.for_footprint(osm)], ['2A'])

    def test_osm_centre_inside_the_register_outline(self):
        osm = [[(5, 5), (15, 5), (15, 15), (5, 15)]]
        near_origin = dict(STORE[0], x=10, z=10)
        with mock.patch.object(B, 'load', return_value=[near_origin]):
            self.assertEqual([b['id'] for b in B.for_footprint(osm)], ['2'])

    def test_far_building_is_not_matched(self):
        self.assertEqual(B.for_footprint([[(300, 300), (310, 300), (310, 310), (300, 310)]]), [])


class Handoff(unittest.TestCase):
    def test_building_facts_lists_only_buildings_with_something(self):
        import site_handoff as H
        self.assertEqual(H.building_facts([row('9', 1, 1)]), [])
        lines = H.building_facts([row('2', 1, 1, 'https://d.example/image-archive/buildings/200/2.jpg')])
        self.assertIn('University building', lines[0])
        self.assertIn('/800/2.jpg', lines[1])


if __name__ == '__main__':
    unittest.main()
