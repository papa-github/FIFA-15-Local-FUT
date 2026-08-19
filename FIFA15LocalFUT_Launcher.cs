// FIFA 15 Local FUT - Steam launcher
//
// Built as a windowed (no-console) exe so it can be added to Steam as a
// non-Steam game with a real name and icon. It exists because the normal
// PLAY_LOCAL_FUT15.cmd is unusable from Steam for two reasons:
//
//   1. It self-elevates. Steam Input injects into the game process, and an
//      unelevated Steam cannot inject into an elevated fifa15.exe.
//   2. It detaches and exits immediately, so Steam marks the shortcut as
//      stopped and unloads the controller config mid-session.
//
// This process never elevates and stays alive until fifa15.exe exits.
//
// Build: BUILD_LAUNCHER.cmd   (uses the csc.exe shipped with Windows)

using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("FIFA 15 Local FUT")]
[assembly: AssemblyProduct("FIFA 15 Local FUT")]
[assembly: AssemblyDescription("Starts the local FUT services and FIFA 15.")]
[assembly: AssemblyCompany("FIFA 15 Local FUT")]
[assembly: AssemblyVersion("0.2.39.0")]
[assembly: AssemblyFileVersion("0.2.39.0")]

static class Launcher
{
    const string AppName = "FIFA 15 Local FUT";
    const int ReadyTimeoutSeconds = 90;

    // Origin's LSX port. Local FUT must own this to emulate the Origin auth
    // handshake. If EA App is running it holds 3216, server.py silently takes
    // its "external LSX passthrough" branch, and the game asks the real EA App
    // for its auth token instead. The login is then never attempted and FIFA
    // reports "Your title version is outdated" with nothing useful in the log.
    const int LsxPort = 3216;

    static readonly string[] EaProcessNames =
    {
        "EADesktop", "EACefSubProcess", "desktop_proxy",
        "EALocalHostSvc", "EABackgroundService",
        "Origin", "OriginWebHelperService", "OriginClientService", "OriginER",
    };

    static string gameDir;
    static string logPath;
    static string launcherLogPath;
    static Process serverProc;

    [STAThread]
    static int Main()
    {
        gameDir = Path.GetDirectoryName(Application.ExecutablePath);

        string runtimeRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FIFA15LocalFUT");
        string logDir = Path.Combine(runtimeRoot, "logs");
        try { Directory.CreateDirectory(logDir); } catch { }
        logPath = Path.Combine(logDir, "steam-launcher-server.log");
        launcherLogPath = Path.Combine(logDir, "steam-launcher.log");

        string gameExe = Path.Combine(gameDir, "fifa15.exe");
        string serverPy = Path.Combine(gameDir, "localfut15", "server.py");

        if (!File.Exists(gameExe) || !File.Exists(serverPy))
        {
            Fail("This launcher must sit in the FIFA 15 folder next to fifa15.exe, " +
                 "with the Local FUT payload already installed.\n\n" +
                 "Run PLAY_LOCAL_FUT15.cmd from the release package once first.\n\n" +
                 "Looked in:\n" + gameDir);
            return 1;
        }

        Log("--- launch requested ---");

        if (!EnsureLsxPortFree())
        {
            Fail("The Origin LSX port " + LsxPort + " is still in use by another program.\n\n" +
                 "Local FUT has to own this port to emulate the Origin login. While " +
                 "something else holds it, FIFA will start but report:\n\n" +
                 "    \"Your title version is outdated.\"\n\n" +
                 "Close whatever is using port " + LsxPort + " and try again.\n\n" +
                 "Launcher log:\n" + launcherLogPath);
            return 5;
        }

        StopServer();
        KillGame();

        if (!StartServer())
        {
            Fail("Could not start the Local FUT server process.\n\nSee:\n" + logPath);
            return 3;
        }

        if (!WaitForFutPort(runtimeRoot))
        {
            string tail = ReadLogTail(40);
            StopServer();
            Fail("Local FUT did not become ready, so FIFA 15 was not launched.\n\n" +
                 "Last output from the server:\n\n" + tail + "\n\nFull log:\n" + logPath);
            return 2;
        }

        Log("Local FUT ready; launching fifa15.exe.");

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(gameExe);
            psi.WorkingDirectory = gameDir;
            psi.UseShellExecute = false;
            Process game = Process.Start(psi);
            if (game != null) game.WaitForExit();
        }
        catch (Exception ex)
        {
            StopServer();
            Fail("Could not launch fifa15.exe.\n\n" + ex.Message);
            return 4;
        }

        // Process.WaitForExit can return early if the game re-spawns itself
        // under a new process, so confirm nothing named fifa15 is left.
        while (Process.GetProcessesByName("fifa15").Length > 0)
            Thread.Sleep(3000);

        StopServer();
        return 0;
    }

    // Runs START_LOCAL_FUT15.cmd hidden, with its console output captured to a
    // log file. Reusing the project's own script keeps the Python/dependency
    // resolution in one place instead of duplicating it here.
    static bool StartServer()
    {
        string script = Path.Combine(gameDir, "START_LOCAL_FUT15.cmd");
        if (!File.Exists(script)) return false;

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo("cmd.exe");
            psi.Arguments = "/c \"\"" + script + "\" > \"" + logPath + "\" 2>&1\"";
            psi.WorkingDirectory = gameDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardInput = true;   // so the script's trailing pause returns
            serverProc = Process.Start(psi);
            if (serverProc == null) return false;
            serverProc.StandardInput.Close();
            return true;
        }
        catch { return false; }
    }

    static void StopServer()
    {
        RunHidden(Path.Combine(gameDir, "STOP_LOCAL_FUT15.cmd"), "/quiet", 15000);
        try
        {
            if (serverProc != null && !serverProc.HasExited)
                serverProc.Kill();
        }
        catch { }
        serverProc = null;
    }

    // Closes EA App / Origin if it is holding the LSX port, then waits for the
    // listener to actually disappear. Returns false only if the port is still
    // occupied afterwards, which means launching would fail confusingly.
    static bool EnsureLsxPortFree()
    {
        if (!CanConnect(LsxPort))
        {
            Log("LSX port " + LsxPort + " is free.");
            return true;
        }

        Log("LSX port " + LsxPort + " is in use; closing EA App / Origin.");

        foreach (string name in EaProcessNames)
        {
            foreach (Process p in Process.GetProcessesByName(name))
            {
                try
                {
                    p.Kill();
                    p.WaitForExit(5000);
                    Log("  killed " + name + " (pid " + p.Id + ")");
                }
                catch (Exception ex)
                {
                    Log("  could not kill " + name + ": " + ex.Message);
                }
            }
        }

        // EA App tears down its helpers asynchronously, so poll rather than
        // assuming the socket is released the moment the process exits.
        for (int i = 0; i < 30 && CanConnect(LsxPort); i++)
            Thread.Sleep(500);

        bool free = !CanConnect(LsxPort);
        Log(free ? "LSX port " + LsxPort + " released."
                 : "LSX port " + LsxPort + " STILL held after closing EA App.");
        return free;
    }

    static void Log(string line)
    {
        try
        {
            File.AppendAllText(launcherLogPath,
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + line + Environment.NewLine);
        }
        catch { }
    }

    static void KillGame()
    {
        foreach (Process p in Process.GetProcessesByName("fifa15"))
        {
            try { p.Kill(); p.WaitForExit(5000); } catch { }
        }
    }

    static void RunHidden(string script, string args, int timeoutMs)
    {
        if (!File.Exists(script)) return;
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo("cmd.exe");
            psi.Arguments = "/c \"\"" + script + "\" " + args + "\"";
            psi.WorkingDirectory = gameDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardInput = true;
            Process p = Process.Start(psi);
            if (p != null)
            {
                p.StandardInput.Close();
                p.WaitForExit(timeoutMs);
            }
        }
        catch { }
    }

    // The server writes runtime_ports.json once it has claimed its ports, which
    // may differ from the defaults if Windows has reserved one of them.
    static bool WaitForFutPort(string runtimeRoot)
    {
        string portsFile = Path.Combine(runtimeRoot, "runtime_ports.json");
        DateTime deadline = DateTime.UtcNow.AddSeconds(ReadyTimeoutSeconds);

        while (DateTime.UtcNow < deadline)
        {
            if (serverProc != null && serverProc.HasExited) return false;

            int port = ReadFutPort(portsFile);
            if (port > 0 && CanConnect(port)) return true;

            Thread.Sleep(500);
        }
        return false;
    }

    static int ReadFutPort(string portsFile)
    {
        try
        {
            if (!File.Exists(portsFile)) return 0;
            string json;
            using (FileStream fs = new FileStream(portsFile, FileMode.Open,
                       FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (StreamReader sr = new StreamReader(fs))
                json = sr.ReadToEnd();

            Match m = Regex.Match(json, "\"fut_port\"\\s*:\\s*(\\d+)");
            if (!m.Success) return 0;
            return int.Parse(m.Groups[1].Value);
        }
        catch { return 0; }
    }

    static bool CanConnect(int port)
    {
        try
        {
            using (TcpClient c = new TcpClient())
            {
                IAsyncResult ar = c.BeginConnect("127.0.0.1", port, null, null);
                if (!ar.AsyncWaitHandle.WaitOne(400)) return false;
                c.EndConnect(ar);
                return true;
            }
        }
        catch { return false; }
    }

    static string ReadLogTail(int lines)
    {
        try
        {
            if (!File.Exists(logPath)) return "(no server log was produced)";
            string[] all;
            using (FileStream fs = new FileStream(logPath, FileMode.Open,
                       FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (StreamReader sr = new StreamReader(fs))
                all = sr.ReadToEnd().Replace("\r\n", "\n").Split('\n');

            int start = Math.Max(0, all.Length - lines);
            return string.Join(Environment.NewLine, all, start, all.Length - start).Trim();
        }
        catch { return "(could not read the server log)"; }
    }

    static void Fail(string message)
    {
        MessageBox.Show(message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
