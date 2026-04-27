# Valheim Modding — Configuration

---

## BepInEx Config.Bind (Simple, Auto-Generates .cfg)

```csharp
private ConfigEntry<float>  _myFloat;
private ConfigEntry<string> _myString;
private ConfigEntry<bool>   _myBool;

// In Awake():
_myFloat  = Config.Bind("SectionName", "KeyName",   10f,          "Description.");
_myString = Config.Bind("Messages",    "RainStart",  "Rain!",      "Shown when rain starts.");
_myBool   = Config.Bind("General",     "Enabled",    true,         "Enable the mod.");

// Usage:
float val  = _myFloat.Value;
string msg = _myString.Value;
```

Config file is named after `PluginGUID` — keep GUID simple (e.g. `"raindance"`)
to get `raindance.cfg` instead of `com.yourname.raindance.cfg`.

⚠️ BepInEx config changes are **not hot-reloaded** — the server must restart to pick them up.

---

## Custom .cfg Format (for non-standard data like scheduled entries)

Example format:
```
# Comment
timezone=10
welcome=Hello Vikings!
welcome-delay=30
09:00 Good morning!
23:30 Server restart in 30 minutes.
```

### Parsing

```csharp
foreach (string raw in File.ReadAllLines(configPath))
{
    string line = raw.Trim();
    if (string.IsNullOrEmpty(line) || line.StartsWith("#")) continue;

    if (line.StartsWith("timezone="))
    {
        int.TryParse(line.Substring("timezone=".Length).Trim(), out timezone);
        continue;
    }

    int space = line.IndexOf(' ');
    if (space < 0) continue;
    string time = line.Substring(0, space).Trim();
    string text = line.Substring(space + 1).Trim();
    // store scheduled entry...
}
```

---

## Live Reload with FileSystemWatcher

```csharp
private FileSystemWatcher _configWatcher;
private DateTime _lastConfigReload = DateTime.MinValue;

private void StartConfigWatcher()
{
    _configWatcher = new FileSystemWatcher(Paths.ConfigPath, "mymod.cfg");
    _configWatcher.NotifyFilter = NotifyFilters.LastWrite;
    _configWatcher.Changed += OnConfigChanged;
    _configWatcher.EnableRaisingEvents = true;
}

private void OnConfigChanged(object sender, FileSystemEventArgs e)
{
    // FileSystemWatcher fires twice on save (content write + metadata write) — debounce
    if ((DateTime.Now - _lastConfigReload).TotalSeconds < 1) return;
    _lastConfigReload = DateTime.Now;
    System.Threading.Thread.Sleep(200); // wait for file write to complete
    Log.LogInfo("Config reloaded.");
    LoadConfig();
}
```

The 1-second debounce suppresses the duplicate event. The 200ms sleep prevents reading
a partially-written file.

---

## Config File Location

BepInEx config files live in:
```
BepInEx/config/<PluginGUID>.cfg
```

From code, use `Paths.ConfigPath` for the directory — don't hardcode the path.
