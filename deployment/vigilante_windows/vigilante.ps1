# vigilante.ps1 - vigilante EXTERNO de pciq22 (item 59b, parte externa).
# Corre en el PC Windows del laboratorio (PCIQ74) cada 2 h con el Programador de tareas.
# Comprueba desde fuera: Streamlit privado :8501, publico :8502 y el proxy de Ollama :11434
# (debe responder 401 sin token: asi no hace falta guardar ningun secreto aqui).
# Envia correo por SMTP sin autenticacion (smtp.uca.es:25) cuando:
#   - hay $UmbralFallos comprobaciones seguidas con fallo (alerta)
#   - vuelve a estar todo bien tras una alerta (recuperacion)
#   - sigue caido: un recordatorio cada 24 h
# Solo ASCII a proposito (PowerShell 5.1 lee mal UTF-8 sin BOM).

$Destino      = 'martin.ramirez@gm.uca.es'
$Remitente    = 'vigilante-pciq74@uca.es'
$Smtp         = 'smtp.uca.es'
$Host_        = 'pciq22.uca.es'
$UmbralFallos = 2
$Estado       = Join-Path $env:ProgramData 'vigilante_pciq22\estado.json'

$checks = @(
    @{ Nombre = 'Streamlit privado :8501'; Url = "http://${Host_}:8501/_stcore/health"; Codigo = 200 },
    @{ Nombre = 'Streamlit publico :8502'; Url = "http://${Host_}:8502/_stcore/health"; Codigo = 200 },
    @{ Nombre = 'Proxy Ollama :11434 (401 sin token)'; Url = "http://${Host_}:11434/api/version"; Codigo = 401 }
)

function Get-Codigo($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

$fallos = @()
foreach ($c in $checks) {
    $got = Get-Codigo $c.Url
    if ($got -ne $c.Codigo) {
        $txt = if ($got -eq 0) { 'sin conexion' } else { "HTTP $got" }
        $fallos += "$($c.Nombre): $txt (esperado $($c.Codigo))"
    }
}

# Estado previo
$prev = @{ seguidos = 0; alertado = $false; ultimo_aviso = '2000-01-01T00:00:00' }
if (Test-Path $Estado) {
    try { $j = Get-Content $Estado -Raw | ConvertFrom-Json
          $prev = @{ seguidos = [int]$j.seguidos; alertado = [bool]$j.alertado; ultimo_aviso = [string]$j.ultimo_aviso } } catch {}
}

function Enviar($asunto, $cuerpo) {
    try {
        Send-MailMessage -From $Remitente -To $Destino -Subject $asunto -Body $cuerpo -SmtpServer $Smtp -Port 25 -Encoding UTF8
        return $true
    } catch {
        Write-Host "No se pudo enviar el correo: $($_.Exception.Message)"
        return $false
    }
}

$ahora = Get-Date
$seguidos = $prev.seguidos; $alertado = $prev.alertado; $ultimo = [datetime]$prev.ultimo_aviso

if ($fallos.Count -gt 0) {
    $seguidos++
    Write-Output ("[{0}] FALLO ({1} seguidos): {2}" -f $ahora, $seguidos, ($fallos -join ' | '))
    $detalle = "Desde PCIQ74 no responde correctamente ${Host_}:`r`n - " + ($fallos -join "`r`n - ")
    if ($seguidos -ge $UmbralFallos -and -not $alertado) {
        if (Enviar "[research_agent] pciq22 CAIDO" $detalle) { $alertado = $true; $ultimo = $ahora }
    } elseif ($alertado -and ($ahora - $ultimo).TotalHours -ge 24) {
        if (Enviar "[research_agent] pciq22 sigue CAIDO" $detalle) { $ultimo = $ahora }
    }
} else {
    Write-Output ("[{0}] OK" -f $ahora)
    if ($alertado) { Enviar "[research_agent] pciq22 recuperado" "Todas las comprobaciones vuelven a pasar." | Out-Null }
    $seguidos = 0; $alertado = $false
}

New-Item -ItemType Directory -Force -Path (Split-Path $Estado) | Out-Null
@{ seguidos = $seguidos; alertado = $alertado; ultimo_aviso = $ultimo.ToString('s') } | ConvertTo-Json | Set-Content $Estado
