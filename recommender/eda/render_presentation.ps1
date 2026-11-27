param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$Slides = ""
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $InputFile -PathType Leaf)) {
    throw "Presentation input does not exist"
}
$app = New-Object -ComObject PowerPoint.Application
$presentation = $null
try {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $presentation = $app.Presentations.Open($InputFile, -1, 0, 0)
    $indices = if ($Slides) { $Slides.Split(',') | ForEach-Object { [int]$_ } } else { 1..$presentation.Slides.Count }
    foreach ($index in $indices) {
        $slide = $presentation.Slides.Item($index)
        $target = Join-Path $OutputDir ("slide_{0:D2}.png" -f $index)
        $slide.Export($target, "PNG", 1600, 900)
    }
    $bounds = @()
    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                $range = $shape.TextFrame.TextRange
                if ($range.BoundTop + $range.BoundHeight -gt $shape.Top + $shape.Height + 3) {
                    $bounds += "Slide $($slide.SlideIndex): $($shape.Name) exceeds text box height"
                }
            }
            if ($shape.HasTable -eq -1) {
                for ($row = 1; $row -le $shape.Table.Rows.Count; $row++) {
                    for ($column = 1; $column -le $shape.Table.Columns.Count; $column++) {
                        $cell = $shape.Table.Cell($row, $column).Shape
                        $range = $cell.TextFrame.TextRange
                        if ($range.BoundTop + $range.BoundHeight -gt $cell.Top + $cell.Height + 3) {
                            $bounds += "Slide $($slide.SlideIndex): table cell $row,$column exceeds height"
                        }
                    }
                }
            }
        }
    }
    @{slide_count=$presentation.Slides.Count; exported=@($indices); text_height_warnings=$bounds} | ConvertTo-Json -Depth 4
} finally {
    if ($presentation) { $presentation.Close() }
    if ($app.Presentations.Count -eq 0) { $app.Quit() }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
