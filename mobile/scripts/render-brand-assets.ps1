# Rasterize the repository's Awinlink monogram geometry for native build assets.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$assetDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../assets/images'))
function Write-AwinlinkMark([string] $name, [bool] $background, [bool] $blueMark) {
    $bitmap = New-Object Drawing.Bitmap 1024,1024
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $blue = [Drawing.ColorTranslator]::FromHtml('#2458d3')
        $graphics.Clear($(if ($background) { $blue } else { [Drawing.Color]::Transparent }))
        $path = New-Object Drawing.Drawing2D.GraphicsPath
        try {
            $outline = [Drawing.PointF[]]@(
                [Drawing.PointF]::new(300,780), [Drawing.PointF]::new(430,250),
                [Drawing.PointF]::new(594,250), [Drawing.PointF]::new(724,780),
                [Drawing.PointF]::new(594,780), [Drawing.PointF]::new(565,650),
                [Drawing.PointF]::new(459,650), [Drawing.PointF]::new(430,780))
            $path.AddPolygon($outline)
            $path.AddPolygon([Drawing.PointF[]]@([Drawing.PointF]::new(480,540),[Drawing.PointF]::new(544,540),[Drawing.PointF]::new(512,380)))
            $brush = New-Object Drawing.SolidBrush $(if ($blueMark) { $blue } else { [Drawing.Color]::White })
            try { $graphics.FillPath($brush, $path) } finally { $brush.Dispose() }
        } finally { $path.Dispose() }
        $bitmap.Save((Join-Path $assetDirectory $name), [Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
Write-AwinlinkMark 'awinlink-icon.png' $true $false
Write-AwinlinkMark 'awinlink-foreground.png' $false $false
Write-AwinlinkMark 'awinlink-splash.png' $false $true
