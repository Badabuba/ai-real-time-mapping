param([string]$Pptx, [string]$Pdf, [string]$PngDir)
$ErrorActionPreference = "Stop"
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($Pptx, $true, $false, $false)  # read-only, no window
    "slides=" + $pres.Slides.Count
    foreach ($slide in $pres.Slides) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.Type -eq 16) {  # msoMedia
                "slide " + $slide.SlideIndex + " media: type=" + $shape.MediaType + " name=" + $shape.Name +
                    " length_ms=" + $shape.MediaFormat.Length + " embedded=" + $shape.MediaFormat.IsEmbedded
            }
        }
    }
    $pres.SaveAs($Pdf, 32)
    New-Item -ItemType Directory -Force $PngDir | Out-Null
    foreach ($slide in $pres.Slides) {
        $slide.Export((Join-Path $PngDir ("slide-" + $slide.SlideIndex + ".png")), "PNG", 1920, 1080)
    }
    $pres.Close()
} finally {
    $app.Quit()
}
