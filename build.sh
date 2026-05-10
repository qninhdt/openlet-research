#!/bin/bash
set -e

# Chuyển vào thư mục chứa mã nguồn LaTeX
cd docs/reports

MAIN="thesis"
BUILD="build"
TEX="pdflatex -shell-escape -interaction=nonstopmode -halt-on-error -output-directory=$BUILD"

echo "Tạo thư mục build..."
mkdir -p "$BUILD"

echo "Chạy pdflatex lần 1..."
$TEX "$MAIN.tex"

echo "Chạy bibtex và makeindex..."
cd "$BUILD"
BIBINPUTS=..: bibtex "$MAIN" || true
makeindex -s "$MAIN.ist" -t "$MAIN.glg" -o "$MAIN.gls" "$MAIN.glo" 2>/dev/null || true
makeindex -o concepts.ind concepts.idx 2>/dev/null || true
makeindex -o repos.ind repos.idx 2>/dev/null || true
cd ..

echo "Chạy pdflatex lần 2..."
$TEX "$MAIN.tex"

echo "Chạy pdflatex lần 3..."
$TEX "$MAIN.tex"

echo "Copy kết quả ra report.pdf..."
cp "$BUILD/$MAIN.pdf" "../../report.pdf"

echo "Build thành công! File output được lưu ở ./report.pdf"
