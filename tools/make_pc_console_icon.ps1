Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"
$outDir = Split-Path -Parent $PSScriptRoot
$previewPath = Join-Path $outDir "pc-console-icon.png"
$iconPath = Join-Path $outDir "pc-console-icon.ico"

function New-RoundedRectPath {
  param(
    [float]$X,
    [float]$Y,
    [float]$Width,
    [float]$Height,
    [float]$Radius
  )

  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $diameter = $Radius * 2
  $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
  $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
  $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
  $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
  $path.CloseFigure()
  return $path
}

function New-Pen {
  param(
    [System.Drawing.Color]$Color,
    [float]$Width
  )

  $pen = [System.Drawing.Pen]::new($Color, $Width)
  $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
  $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
  $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
  return $pen
}

function Draw-Icon {
  param([int]$Size)

  $scale = $Size / 256.0
  $bitmap = New-Object System.Drawing.Bitmap($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $graphics.Clear([System.Drawing.Color]::Transparent)

  function Pt {
    param([float]$X, [float]$Y)
    return [System.Drawing.PointF]::new([float]($X * $scale), [float]($Y * $scale))
  }

  function RectF {
    param([float]$X, [float]$Y, [float]$Width, [float]$Height)
    return [System.Drawing.RectangleF]::new(
      [float]($X * $scale),
      [float]($Y * $scale),
      [float]($Width * $scale),
      [float]($Height * $scale)
    )
  }

  $bgPath = New-RoundedRectPath 0 0 $Size $Size (42 * $scale)
  $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    ([System.Drawing.RectangleF]::new(0, 0, $Size, $Size)),
    [System.Drawing.Color]::FromArgb(255, 19, 50, 92),
    [System.Drawing.Color]::FromArgb(255, 6, 15, 34),
    55
  )
  $graphics.FillPath($bgBrush, $bgPath)

  $shadowBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(70, 0, 0, 0))
  $graphics.FillEllipse($shadowBrush, 75 * $scale, 196 * $scale, 106 * $scale, 14 * $scale)

  $standPath = New-Object System.Drawing.Drawing2D.GraphicsPath
  $standPath.AddPolygon(@(
    (Pt 112 169),
    (Pt 145 169),
    (Pt 154 199),
    (Pt 168 203),
    (Pt 88 203),
    (Pt 102 199)
  ))
  $standBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (RectF 86 168 84 38),
    [System.Drawing.Color]::FromArgb(255, 236, 240, 245),
    [System.Drawing.Color]::FromArgb(255, 104, 113, 126),
    90
  )
  $graphics.FillPath($standBrush, $standPath)

  $basePath = New-RoundedRectPath (83 * $scale) (200 * $scale) (90 * $scale) (14 * $scale) (5 * $scale)
  $baseBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (RectF 83 199 90 16),
    [System.Drawing.Color]::FromArgb(255, 245, 248, 252),
    [System.Drawing.Color]::FromArgb(255, 131, 141, 154),
    90
  )
  $graphics.FillPath($baseBrush, $basePath)

  $framePath = New-RoundedRectPath (39 * $scale) (46 * $scale) (178 * $scale) (132 * $scale) (13 * $scale)
  $frameBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (RectF 39 46 178 132),
    [System.Drawing.Color]::FromArgb(255, 246, 250, 255),
    [System.Drawing.Color]::FromArgb(255, 122, 132, 146),
    90
  )
  $graphics.FillPath($frameBrush, $framePath)
  $framePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(180, 255, 255, 255), [float](2 * $scale))
  $graphics.DrawPath($framePen, $framePath)

  $screenPath = New-RoundedRectPath (52 * $scale) (58 * $scale) (152 * $scale) (94 * $scale) (7 * $scale)
  $screenBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (RectF 52 58 152 94),
    [System.Drawing.Color]::FromArgb(255, 20, 45, 83),
    [System.Drawing.Color]::FromArgb(255, 5, 12, 27),
    80
  )
  $graphics.FillPath($screenBrush, $screenPath)
  $screenPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(190, 0, 0, 0), [float](2 * $scale))
  $graphics.DrawPath($screenPen, $screenPath)

  $glowPen = New-Pen ([System.Drawing.Color]::FromArgb(95, 0, 94, 255)) (15 * $scale)
  $codeBorder = New-Pen ([System.Drawing.Color]::FromArgb(220, 0, 72, 210)) (10 * $scale)
  $codePen = New-Pen ([System.Drawing.Color]::FromArgb(255, 87, 213, 255)) (7 * $scale)
  $highlightPen = New-Pen ([System.Drawing.Color]::FromArgb(190, 207, 248, 255)) (2.2 * $scale)

  foreach ($pen in @($glowPen, $codeBorder, $codePen)) {
    $graphics.DrawLines($pen, @(
      (Pt 107 88),
      (Pt 84 106),
      (Pt 107 124)
    ))
    $graphics.DrawLine($pen, 139 * $scale, 81 * $scale, 121 * $scale, 132 * $scale)
    $graphics.DrawLines($pen, @(
      (Pt 149 88),
      (Pt 172 106),
      (Pt 149 124)
    ))
  }

  $graphics.DrawLine($highlightPen, 139 * $scale, 82 * $scale, 133 * $scale, 99 * $scale)
  $graphics.DrawLine($highlightPen, 101 * $scale, 92 * $scale, 87 * $scale, 103 * $scale)
  $graphics.DrawLine($highlightPen, 155 * $scale, 92 * $scale, 169 * $scale, 103 * $scale)

  $graphics.Dispose()
  return $bitmap
}

function Get-PngBytes {
  param([System.Drawing.Bitmap]$Bitmap)
  $stream = New-Object System.IO.MemoryStream
  $Bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
  $bytes = $stream.ToArray()
  $stream.Dispose()
  return $bytes
}

$preview = Draw-Icon 1024
$preview.Save($previewPath, [System.Drawing.Imaging.ImageFormat]::Png)
$preview.Dispose()

$sizes = @(256, 128, 64, 48, 32, 16)
$images = @()
foreach ($size in $sizes) {
  $bitmap = Draw-Icon $size
  $images += [pscustomobject]@{ Size = $size; Bytes = [byte[]](Get-PngBytes $bitmap) }
  $bitmap.Dispose()
}

$file = [System.IO.File]::Create($iconPath)
$writer = New-Object System.IO.BinaryWriter($file)
$writer.Write([UInt16]0)
$writer.Write([UInt16]1)
$writer.Write([UInt16]$images.Count)

$offset = 6 + (16 * $images.Count)
foreach ($image in $images) {
  $dimension = if ($image.Size -eq 256) { 0 } else { $image.Size }
  $writer.Write([byte]$dimension)
  $writer.Write([byte]$dimension)
  $writer.Write([byte]0)
  $writer.Write([byte]0)
  $writer.Write([UInt16]1)
  $writer.Write([UInt16]32)
  $writer.Write([UInt32]$image.Bytes.Length)
  $writer.Write([UInt32]$offset)
  $offset += $image.Bytes.Length
}

foreach ($image in $images) {
  $bytes = [byte[]]$image.Bytes
  $writer.Write($bytes, 0, $bytes.Length)
}

$writer.Close()
$file.Close()

[pscustomobject]@{
  Icon = $iconPath
  Preview = $previewPath
}
