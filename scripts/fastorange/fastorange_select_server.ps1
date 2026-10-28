# Select a server on FastOrange. Optional levels: -Tab <group> -Country <region|alias> -Name <node>.
# Defaults: Tab=VIP专享版, Country=日本 (this user's usual choice).
# -Country accepts English aliases to avoid command-line encoding issues (japan, singapore, usa, ...).
# Auto-disconnects first if connected (the app forbids switching while connected);
# selecting a node triggers auto-reconnect, and this script waits for the terminal state.
param(
    [string]$Tab = "VIP专享版",
    [string]$Country = "日本",
    [string]$Name = ""
)

$countryAliases = @{
    japan = "日本";       singapore = "新加坡"; usa = "美国";       us = "美国"
    uk = "英国";          germany = "德国";     netherlands = "荷兰"
    korea = "韩国";       hongkong = "香港";    hk = "香港"
    uae = "阿联酋";       australia = "澳大利亚"; india = "印度"
    canada = "加拿大";    finland = "芬兰";     poland = "波兰";    norway = "挪威"
}
if ($Country -and $countryAliases.ContainsKey($Country.ToLower())) {
    $Country = $countryAliases[$Country.ToLower()]
}
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$proc = Get-Process -Name FastOrange -ErrorAction Stop
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)

function Get-State([System.Windows.Automation.AutomationElement]$rootEl) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ConnectBtnText")
    $tb = $rootEl.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($tb) { return $tb.Current.Name } else { return $null }
}

function Invoke-ButtonByText([System.Windows.Automation.AutomationElement]$rootEl, [string]$text) {
    # find a visible TextBlock by exact name, walk up to the first invokable ancestor
    $nameCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $text)
    $tb = $rootEl.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
    if ($tb -eq $null) { throw "text '" + $text + "' not found" }
    $el = $tb
    while ($el -ne $null) {
        try {
            $p = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            if ($p -ne $null) { $p.Invoke(); return }
        } catch { }
        $el = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($el)
    }
    throw "no invokable ancestor for '" + $text + "'"
}

function Get-VisibleServerItems([System.Windows.Automation.AutomationElement]$rootEl) {
    $itemCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, "ListBoxItem")
    $items = $rootEl.FindAll([System.Windows.Automation.TreeScope]::Descendants, $itemCond)
    $result = @()
    foreach ($it in $items) {
        if ($it.Current.ClassName -ne "ListBoxItem") { continue }
        if ($it.Current.IsOffscreen) { continue }  # ghosts from other tabs/pages linger in the tree
        if ($it.Current.Name -notmatch "ServerDto") { continue }
        $labels = @()
        $texts = $it.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($t in $texts) { if ($t.Current.Name -and $t.Current.Name.Trim()) { $labels += $t.Current.Name } }
        if ($labels.Count -gt 0) {
            $result += [PSCustomObject]@{ Labels = ($labels -join " | "); Element = $it }
        }
    }
    return $result
}

function Select-ServerItem($item) {
    try {
        $sp = $item.Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        if ($sp -ne $null) { $sp.Select(); return "SelectionItemPattern" }
    } catch { }
    $el = $item.Element
    while ($el -ne $null) {
        try {
            $p = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            if ($p -ne $null) { $p.Invoke(); return "InvokePattern" }
        } catch { }
        $el = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($el)
    }
    throw "cannot select item: " + $item.Labels
}

function Find-Item([string]$label) {
    $vis = Get-VisibleServerItems $root
    $hit = $vis | Where-Object { $_.Labels -eq $label } | Select-Object -First 1
    if ($hit -eq $null) { $hit = $vis | Where-Object { $_.Labels -like ("*" + $label + "*") } | Select-Object -First 1 }
    return $hit
}

# 0. wait out any in-flight connecting state
$state = Get-State $root
for ($i = 0; $i -lt 20 -and $state -eq "正在连接..."; $i++) {
    Start-Sleep -Seconds 3
    $state = Get-State $root
}

# 1. disconnect if connected (node switching requires it)
if ($state -eq "断开连接") {
    Write-Output "connected -> disconnecting first"
    Invoke-ButtonByText $root "断开连接"
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 2
        $state = Get-State $root
        if ($state -eq "连接") { break }
    }
    if ($state -ne "连接") { throw "failed to disconnect before switching (state '" + $state + "')" }
    Write-Output "disconnected"
}

# 2. open the server page if not already open
$nlCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "节点列表")
$nl = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nlCond)
if ($nl -eq $null -or $nl.Current.IsOffscreen) {
    $csCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ChooseServerBtn")
    $cs = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $csCond)
    if ($cs -eq $null -or -not $cs.Current.IsEnabled) { throw "ChooseServerBtn missing/disabled; cannot open server page" }
    $cs.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Seconds 2
    Write-Output "opened server page"
}

# 3. switch tab group
if ($Tab) {
    Invoke-ButtonByText $root $Tab
    Start-Sleep -Seconds 2
    Write-Output ("switched tab: " + $Tab)
}

# 4. enter country/region
if ($Country) {
    $hit = Find-Item $Country
    if ($hit -eq $null) {
        Write-Output ("country '" + $Country + "' not visible. Visible items:")
        Get-VisibleServerItems $root | ForEach-Object { Write-Output ("  " + $_.Labels) }
        exit 4
    }
    $how = Select-ServerItem $hit
    Start-Sleep -Seconds 2
    Write-Output ("entered country '" + $Country + "' via " + $how)
    if (-not $Name) {
        Write-Output "nodes now visible:"
        Get-VisibleServerItems $root | ForEach-Object { Write-Output ("  " + $_.Labels) }
        exit 0
    }
}

# 5. pick the node
if ($Name) {
    $hit = Find-Item $Name
    if ($hit -eq $null) {
        Write-Output ("node '" + $Name + "' not visible. Visible items:")
        Get-VisibleServerItems $root | ForEach-Object { Write-Output ("  " + $_.Labels) }
        exit 4
    }
    Write-Output ("picking node: " + $hit.Labels)
    $how = Select-ServerItem $hit
    Write-Output ("selected via " + $how + " — app auto-connects now, waiting...")

    $last = ""
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 3
        $state = Get-State $root
        if ($state -ne $last) { Write-Output ("t+" + (($i+1)*3) + "s: '" + $state + "'"); $last = $state }
        if ($state -eq "断开连接" -or $state -eq "连接") { break }
    }
    $snCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ServerNameText")
    $sn = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $snCond)
    Write-Output ("ServerNameText: '" + $sn.Current.Name + "'")
    if ($state -eq "断开连接") { Write-Output ("RESULT: connected on " + $hit.Labels); exit 0 }
    if ($state -eq "连接")     { Write-Output "RESULT: selection made but connect failed/aborted"; exit 2 }
    Write-Output ("RESULT: timeout, last state '" + $state + "'")
    exit 3
}

Write-Output "nothing selected (-Name not given). Visible items:"
Get-VisibleServerItems $root | ForEach-Object { Write-Output ("  " + $_.Labels) }
