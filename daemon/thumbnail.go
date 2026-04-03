package main

import (
	"bytes"
	"image"
	"image/jpeg"
	_ "image/png"

	"golang.org/x/image/draw"
)

const thumbnailMaxDim = 72

func generateThumbnail(data []byte) []byte {
	img, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return nil
	}

	bounds := img.Bounds()
	w, h := bounds.Dx(), bounds.Dy()
	if w == 0 || h == 0 {
		return nil
	}

	var newW, newH int
	if w > h {
		newW = thumbnailMaxDim
		newH = h * thumbnailMaxDim / w
	} else {
		newH = thumbnailMaxDim
		newW = w * thumbnailMaxDim / h
	}
	if newW == 0 {
		newW = 1
	}
	if newH == 0 {
		newH = 1
	}

	dst := image.NewRGBA(image.Rect(0, 0, newW, newH))
	draw.BiLinear.Scale(dst, dst.Bounds(), img, bounds, draw.Over, nil)

	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, dst, &jpeg.Options{Quality: 60}); err != nil {
		return nil
	}
	return buf.Bytes()
}
