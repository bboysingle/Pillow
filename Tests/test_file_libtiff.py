from __future__ import print_function
from helper import unittest, PillowTestCase, hopper, py3

from ctypes import c_float
import io
import logging
import itertools
import os

from PIL import Image, TiffImagePlugin, TiffTags

logger = logging.getLogger(__name__)


class LibTiffTestCase(PillowTestCase):

    def setUp(self):
        codecs = dir(Image.core)

        if "libtiff_encoder" not in codecs or "libtiff_decoder" not in codecs:
            self.skipTest("tiff support not available")

    def _assert_noerr(self, im):
        """Helper tests that assert basic sanity about the g4 tiff reading"""
        # 1 bit
        self.assertEqual(im.mode, "1")

        # Does the data actually load
        im.load()
        im.getdata()

        try:
            self.assertEqual(im._compression, 'group4')
        except:
            print("No _compression")
            print(dir(im))

        # can we write it back out, in a different form.
        out = self.tempfile("temp.png")
        im.save(out)


class TestFileLibTiff(LibTiffTestCase):

    def test_g4_tiff(self):
        """Test the ordinary file path load path"""

        test_file = "Tests/images/hopper_g4_500.tif"
        im = Image.open(test_file)

        self.assertEqual(im.size, (500, 500))
        self._assert_noerr(im)

    def test_g4_large(self):
        test_file = "Tests/images/pport_g4.tif"
        im = Image.open(test_file)
        self._assert_noerr(im)

    def test_g4_tiff_file(self):
        """Testing the string load path"""

        test_file = "Tests/images/hopper_g4_500.tif"
        with open(test_file, 'rb') as f:
            im = Image.open(f)

            self.assertEqual(im.size, (500, 500))
            self._assert_noerr(im)

    def test_g4_tiff_bytesio(self):
        """Testing the stringio loading code path"""
        test_file = "Tests/images/hopper_g4_500.tif"
        s = io.BytesIO()
        with open(test_file, 'rb') as f:
            s.write(f.read())
            s.seek(0)
        im = Image.open(s)

        self.assertEqual(im.size, (500, 500))
        self._assert_noerr(im)

    def test_g4_eq_png(self):
        """ Checking that we're actually getting the data that we expect"""
        png = Image.open('Tests/images/hopper_bw_500.png')
        g4 = Image.open('Tests/images/hopper_g4_500.tif')

        self.assert_image_equal(g4, png)

    # see https://github.com/python-pillow/Pillow/issues/279
    def test_g4_fillorder_eq_png(self):
        """ Checking that we're actually getting the data that we expect"""
        png = Image.open('Tests/images/g4-fillorder-test.png')
        g4 = Image.open('Tests/images/g4-fillorder-test.tif')

        self.assert_image_equal(g4, png)

    def test_g4_write(self):
        """Checking to see that the saved image is the same as what we wrote"""
        test_file = "Tests/images/hopper_g4_500.tif"
        orig = Image.open(test_file)

        out = self.tempfile("temp.tif")
        rot = orig.transpose(Image.ROTATE_90)
        self.assertEqual(rot.size, (500, 500))
        rot.save(out)

        reread = Image.open(out)
        self.assertEqual(reread.size, (500, 500))
        self._assert_noerr(reread)
        self.assert_image_equal(reread, rot)
        self.assertEqual(reread.info['compression'], 'group4')

        self.assertEqual(reread.info['compression'], orig.info['compression'])

        self.assertNotEqual(orig.tobytes(), reread.tobytes())

    def test_adobe_deflate_tiff(self):
        test_file = "Tests/images/tiff_adobe_deflate.tif"
        im = Image.open(test_file)

        self.assertEqual(im.mode, "RGB")
        self.assertEqual(im.size, (278, 374))
        self.assertEqual(
            im.tile[0][:3], ('tiff_adobe_deflate', (0, 0, 278, 374), 0))
        im.load()

    def test_write_metadata(self):
        """ Test metadata writing through libtiff """
        for legacy_api in [False, True]:
            img = Image.open('Tests/images/hopper_g4.tif')
            f = self.tempfile('temp.tiff')

            img.save(f, tiffinfo=img.tag)

            if legacy_api:
                original = img.tag.named()
            else:
                original = img.tag_v2.named()

            # PhotometricInterpretation is set from SAVE_INFO,
            # not the original image.
            ignored = ['StripByteCounts', 'RowsPerStrip', 'PageNumber',
                       'PhotometricInterpretation']

            loaded = Image.open(f)
            if legacy_api:
                reloaded = loaded.tag.named()
            else:
                reloaded = loaded.tag_v2.named()

            for tag, value in itertools.chain(reloaded.items(),
                                              original.items()):
                if tag not in ignored:
                    val = original[tag]
                    if tag.endswith('Resolution'):
                        if legacy_api:
                            self.assertEqual(
                                c_float(val[0][0] / val[0][1]).value,
                                c_float(value[0][0] / value[0][1]).value,
                                msg="%s didn't roundtrip" % tag)
                        else:
                            self.assertEqual(
                                c_float(val).value, c_float(value).value,
                                msg="%s didn't roundtrip" % tag)
                    else:
                        self.assertEqual(
                            val, value, msg="%s didn't roundtrip" % tag)

            # https://github.com/python-pillow/Pillow/issues/1561
            requested_fields = ['StripByteCounts',
                                'RowsPerStrip',
                                'StripOffsets']
            for field in requested_fields:
                self.assertTrue(field in reloaded, "%s not in metadata" % field)

    def test_additional_metadata(self):
        # these should not crash. Seriously dummy data, most of it doesn't make
        # any sense, so we're running up against limits where we're asking
        # libtiff to do stupid things.

        # Get the list of the ones that we should be able to write

        core_items = dict((tag, info) for tag, info in [(s, TiffTags.lookup(s)) for s
                                                        in TiffTags.LIBTIFF_CORE]
                          if info.type is not None)

        # Exclude ones that have special meaning that we're already testing them
        im = Image.open('Tests/images/hopper_g4.tif')
        for tag in im.tag_v2.keys():
            try:
                del(core_items[tag])
            except:
                pass

        # Type codes:
        #     2: "ascii",
        #     3: "short",
        #     4: "long",
        #     5: "rational",
        #     12: "double",
        # type: dummy value
        values = {2: 'test',
                  3: 1,
                  4: 2**20,
                  5: TiffImagePlugin.IFDRational(100, 1),
                  12: 1.05}

        new_ifd = TiffImagePlugin.ImageFileDirectory_v2()
        for tag, info in core_items.items():
            if info.length == 1:
                new_ifd[tag] = values[info.type]
            if info.length == 0:
                new_ifd[tag] = tuple(values[info.type] for _ in range(3))
            else:
                new_ifd[tag] = tuple(values[info.type] for _ in range(info.length))

        # Extra samples really doesn't make sense in this application.
        del(new_ifd[338])

        out = self.tempfile("temp.tif")
        TiffImagePlugin.WRITE_LIBTIFF = True

        im.save(out, tiffinfo=new_ifd)

        TiffImagePlugin.WRITE_LIBTIFF = False

    def test_g3_compression(self):
        i = Image.open('Tests/images/hopper_g4_500.tif')
        out = self.tempfile("temp.tif")
        i.save(out, compression='group3')

        reread = Image.open(out)
        self.assertEqual(reread.info['compression'], 'group3')
        self.assert_image_equal(reread, i)

    def test_little_endian(self):
        im = Image.open('Tests/images/16bit.deflate.tif')
        self.assertEqual(im.getpixel((0, 0)), 480)
        self.assertEqual(im.mode, 'I;16')

        b = im.tobytes()
        # Bytes are in image native order (little endian)
        if py3:
            self.assertEqual(b[0], ord(b'\xe0'))
            self.assertEqual(b[1], ord(b'\x01'))
        else:
            self.assertEqual(b[0], b'\xe0')
            self.assertEqual(b[1], b'\x01')

        out = self.tempfile("temp.tif")
        # out = "temp.le.tif"
        im.save(out)
        reread = Image.open(out)

        self.assertEqual(reread.info['compression'], im.info['compression'])
        self.assertEqual(reread.getpixel((0, 0)), 480)
        # UNDONE - libtiff defaults to writing in native endian, so
        # on big endian, we'll get back mode = 'I;16B' here.

    def test_big_endian(self):
        im = Image.open('Tests/images/16bit.MM.deflate.tif')

        self.assertEqual(im.getpixel((0, 0)), 480)
        self.assertEqual(im.mode, 'I;16B')

        b = im.tobytes()

        # Bytes are in image native order (big endian)
        if py3:
            self.assertEqual(b[0], ord(b'\x01'))
            self.assertEqual(b[1], ord(b'\xe0'))
        else:
            self.assertEqual(b[0], b'\x01')
            self.assertEqual(b[1], b'\xe0')

        out = self.tempfile("temp.tif")
        im.save(out)
        reread = Image.open(out)

        self.assertEqual(reread.info['compression'], im.info['compression'])
        self.assertEqual(reread.getpixel((0, 0)), 480)

    def test_g4_string_info(self):
        """Tests String data in info directory"""
        test_file = "Tests/images/hopper_g4_500.tif"
        orig = Image.open(test_file)

        out = self.tempfile("temp.tif")

        orig.tag[269] = 'temp.tif'
        orig.save(out)

        reread = Image.open(out)
        self.assertEqual('temp.tif', reread.tag_v2[269])
        self.assertEqual('temp.tif', reread.tag[269][0])

    def test_12bit_rawmode(self):
        """ Are we generating the same interpretation
        of the image as Imagemagick is? """
        TiffImagePlugin.READ_LIBTIFF = True
        im = Image.open('Tests/images/12bit.cropped.tif')
        im.load()
        TiffImagePlugin.READ_LIBTIFF = False
        # to make the target --
        # convert 12bit.cropped.tif -depth 16 tmp.tif
        # convert tmp.tif -evaluate RightShift 4 12in16bit2.tif
        # imagemagick will auto scale so that a 12bit FFF is 16bit FFF0,
        # so we need to unshift so that the integer values are the same.

        im2 = Image.open('Tests/images/12in16bit.tif')

        logger.debug("%s", [img.getpixel((0, idx))
                            for img in [im, im2] for idx in range(3)])

        self.assert_image_equal(im, im2)

    def test_blur(self):
        # test case from irc, how to do blur on b/w image
        # and save to compressed tif.
        from PIL import ImageFilter
        out = self.tempfile('temp.tif')
        im = Image.open('Tests/images/pport_g4.tif')
        im = im.convert('L')

        im = im.filter(ImageFilter.GaussianBlur(4))
        im.save(out, compression='tiff_adobe_deflate')

        im2 = Image.open(out)
        im2.load()

        self.assert_image_equal(im, im2)

    def test_compressions(self):
        im = hopper('RGB')
        out = self.tempfile('temp.tif')

        for compression in ('packbits', 'tiff_lzw'):
            im.save(out, compression=compression)
            im2 = Image.open(out)
            self.assert_image_equal(im, im2)

        im.save(out, compression='jpeg')
        im2 = Image.open(out)
        self.assert_image_similar(im, im2, 30)

    def test_cmyk_save(self):
        im = hopper('CMYK')
        out = self.tempfile('temp.tif')

        im.save(out, compression='tiff_adobe_deflate')
        im2 = Image.open(out)
        self.assert_image_equal(im, im2)

    def xtest_bw_compression_w_rgb(self):
        """ This test passes, but when running all tests causes a failure due
            to output on stderr from the error thrown by libtiff. We need to
            capture that but not now"""

        im = hopper('RGB')
        out = self.tempfile('temp.tif')

        self.assertRaises(
            IOError, lambda: im.save(out, compression='tiff_ccitt'))
        self.assertRaises(IOError, lambda: im.save(out, compression='group3'))
        self.assertRaises(IOError, lambda: im.save(out, compression='group4'))

    def test_fp_leak(self):
        im = Image.open("Tests/images/hopper_g4_500.tif")
        fn = im.fp.fileno()

        os.fstat(fn)
        im.load()  # this should close it.
        self.assertRaises(OSError, lambda: os.fstat(fn))
        im = None  # this should force even more closed.
        self.assertRaises(OSError, lambda: os.fstat(fn))
        self.assertRaises(OSError, lambda: os.close(fn))

    def test_multipage(self):
        # issue #862
        TiffImagePlugin.READ_LIBTIFF = True
        im = Image.open('Tests/images/multipage.tiff')
        # file is a multipage tiff,  10x10 green, 10x10 red, 20x20 blue

        im.seek(0)
        self.assertEqual(im.size, (10, 10))
        self.assertEqual(im.convert('RGB').getpixel((0, 0)), (0, 128, 0))
        self.assertTrue(im.tag.next)

        im.seek(1)
        self.assertEqual(im.size, (10, 10))
        self.assertEqual(im.convert('RGB').getpixel((0, 0)), (255, 0, 0))
        self.assertTrue(im.tag.next)

        im.seek(2)
        self.assertFalse(im.tag.next)
        self.assertEqual(im.size, (20, 20))
        self.assertEqual(im.convert('RGB').getpixel((0, 0)), (0, 0, 255))

        TiffImagePlugin.READ_LIBTIFF = False

    def test__next(self):
        TiffImagePlugin.READ_LIBTIFF = True
        im = Image.open('Tests/images/hopper.tif')
        self.assertFalse(im.tag.next)
        im.load()
        self.assertFalse(im.tag.next)

    def test_4bit(self):
        # Arrange
        test_file = "Tests/images/hopper_gray_4bpp.tif"
        original = hopper("L")

        # Act
        TiffImagePlugin.READ_LIBTIFF = True
        im = Image.open(test_file)
        TiffImagePlugin.READ_LIBTIFF = False

        # Assert
        self.assertEqual(im.size, (128, 128))
        self.assertEqual(im.mode, "L")
        self.assert_image_similar(im, original, 7.3)

    def test_gray_semibyte_per_pixel(self):
        test_files = (
            (
                24.8,#epsilon
                (#group
                    "Tests/images/tiff_gray_2_4_bpp/hopper2.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper2I.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper2R.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper2IR.tif",
                )
            ),
            (
                7.3,#epsilon
                (#group
                    "Tests/images/tiff_gray_2_4_bpp/hopper4.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper4I.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper4R.tif",
                    "Tests/images/tiff_gray_2_4_bpp/hopper4IR.tif",
                )
            ),
        )
        original = hopper("L")
        for epsilon, group in test_files:
            im = Image.open(group[0])
            self.assertEqual(im.size, (128, 128))
            self.assertEqual(im.mode, "L")
            self.assert_image_similar(im, original, epsilon)
            for file in group[1:]:
                im2 = Image.open(file)
                self.assertEqual(im2.size, (128, 128))
                self.assertEqual(im2.mode, "L")
                self.assert_image_equal(im, im2)

    def test_save_bytesio(self):
        # PR 1011
        # Test TIFF saving to io.BytesIO() object.

        TiffImagePlugin.WRITE_LIBTIFF = True
        TiffImagePlugin.READ_LIBTIFF = True

        # Generate test image
        pilim = hopper()

        def save_bytesio(compression=None):

            buffer_io = io.BytesIO()
            pilim.save(buffer_io, format="tiff", compression=compression)
            buffer_io.seek(0)

            pilim_load = Image.open(buffer_io)
            self.assert_image_similar(pilim, pilim_load, 0)

        # save_bytesio()
        save_bytesio('raw')
        save_bytesio("packbits")
        save_bytesio("tiff_lzw")

        TiffImagePlugin.WRITE_LIBTIFF = False
        TiffImagePlugin.READ_LIBTIFF = False

    def test_crashing_metadata(self):
        # issue 1597
        im = Image.open('Tests/images/rdf.tif')
        out = self.tempfile('temp.tif')

        TiffImagePlugin.WRITE_LIBTIFF = True
        # this shouldn't crash
        im.save(out, format='TIFF')
        TiffImagePlugin.WRITE_LIBTIFF = False

    def test_page_number_x_0(self):
        # Issue 973
        # Test TIFF with tag 297 (Page Number) having value of 0 0.
        # The first number is the current page number.
        # The second is the total number of pages, zero means not available.
        outfile = self.tempfile("temp.tif")
        # Created by printing a page in Chrome to PDF, then:
        # /usr/bin/gs -q -sDEVICE=tiffg3 -sOutputFile=total-pages-zero.tif
        # -dNOPAUSE /tmp/test.pdf -c quit
        infile = "Tests/images/total-pages-zero.tif"
        im = Image.open(infile)
        # Should not divide by zero
        im.save(outfile)



if __name__ == '__main__':
    unittest.main()

# End of file
