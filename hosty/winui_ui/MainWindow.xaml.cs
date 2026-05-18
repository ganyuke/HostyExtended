using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using winui_ui.Pages;

namespace winui_ui;

public sealed partial class MainWindow : Window
{
    public PythonBackendClient IpcClient { get; private set; }
    private List<ServerModel> _servers = new();

    // Store references to the dynamic menu items so we can remove/update them
    private readonly List<NavigationViewItem> _serverMenuItems = new();
    private NavigationViewItemHeader _serversHeader;
    private NavigationViewItem _createServerItem;

    public MainWindow()
    {
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;
        AppWindow.SetIcon("Assets/AppIcon.ico");

        this.Closed += MainWindow_Closed;

        InitializeBackend();
    }

    private void InitializeBackend()
    {
        IpcClient = new PythonBackendClient();
        IpcClient.BackendReady += IpcClient_BackendReady;
        IpcClient.ServerAdded += (s, data) => Dispatch(() => RefreshServers());
        IpcClient.ServerRemoved += (s, data) => Dispatch(() => RefreshServers());
        IpcClient.ServerChanged += (s, data) => Dispatch(() => RefreshServers());

        // Resolve paths relative to the build output directory
        string baseDir = AppContext.BaseDirectory;
        System.Diagnostics.Debug.WriteLine($"[Hosty] AppContext.BaseDirectory = {baseDir}");

        // Project root: in dev the baseDir is something like
        //   <repo>\hosty\winui_ui\bin\<arch>\Debug\net9.0-windows10.0.26100.0\win-x64\
        // We climb up to find the repo root by looking for the "hosty" package directory.
        string projectRoot = baseDir;
        var probe = new DirectoryInfo(baseDir);
        while (probe != null)
        {
            // Look for the hosty Python package directory (contains __init__.py)
            string hostyPkg = Path.Combine(probe.FullName, "hosty", "__init__.py");
            if (File.Exists(hostyPkg))
            {
                projectRoot = probe.FullName;
                break;
            }
            probe = probe.Parent;
        }

        System.Diagnostics.Debug.WriteLine($"[Hosty] Resolved projectRoot = {projectRoot}");

        string pythonPath = Path.Combine(projectRoot, ".venv", "Scripts", "python.exe");
        if (!File.Exists(pythonPath))
        {
            System.Diagnostics.Debug.WriteLine($"[Hosty] .venv python not found at {pythonPath}, falling back to PATH");
            pythonPath = "python";
        }

        string ipcPath = Path.Combine(projectRoot, "hosty", "win_ipc.py");
        if (!File.Exists(ipcPath))
        {
            System.Diagnostics.Debug.WriteLine($"[Hosty] win_ipc.py not found at {ipcPath}");
        }

        System.Diagnostics.Debug.WriteLine($"[Hosty] pythonPath = {pythonPath}");
        System.Diagnostics.Debug.WriteLine($"[Hosty] ipcPath = {ipcPath}");

        try
        {
            IpcClient.Start(pythonPath, ipcPath, projectRoot);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Failed to start Python IPC: {ex.Message}");
        }
    }

    private void Dispatch(Action action)
    {
        DispatcherQueue.TryEnqueue(() => action());
    }

    private async void IpcClient_BackendReady(object sender, EventArgs e)
    {
        Dispatch(async () => {
            await RefreshServers();
            // Navigate to Home initially
            NavFrame.Navigate(typeof(HomePage));
        });
    }

    private async Task RefreshServers()
    {
        if (IpcClient == null) return;

        try
        {
            var result = await IpcClient.SendRequestAsync("get_servers");
            _servers = JsonSerializer.Deserialize<List<ServerModel>>(result.GetRawText());
            
            BuildServerMenu();
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error refreshing servers: {ex.Message}");
        }
    }

    private void BuildServerMenu()
    {
        // 1. Remove existing dynamic items
        foreach (var item in _serverMenuItems)
        {
            NavView.MenuItems.Remove(item);
        }
        _serverMenuItems.Clear();

        if (_serversHeader != null)
        {
            NavView.MenuItems.Remove(_serversHeader);
        }
        if (_createServerItem != null)
        {
            NavView.MenuItems.Remove(_createServerItem);
        }

        // 2. Add header
        _serversHeader = new NavigationViewItemHeader { Content = "Servers" };
        NavView.MenuItems.Add(_serversHeader);

        // 3. Add Server items
        foreach (var server in _servers)
        {
            var item = new NavigationViewItem
            {
                Content = server.Name,
                Icon = new SymbolIcon(Symbol.Contact), // Placeholder, can be updated to load custom images
                Tag = $"server_{server.Id}"
            };
            NavView.MenuItems.Add(item);
            _serverMenuItems.Add(item);
        }

        // 4. Add "Create Server" item
        _createServerItem = new NavigationViewItem
        {
            Content = "Add Server",
            Icon = new SymbolIcon(Symbol.Add),
            Tag = "create_server"
        };
        NavView.MenuItems.Add(_createServerItem);
    }

    private void TitleBar_PaneToggleRequested(TitleBar sender, object args)
    {
        NavView.IsPaneOpen = !NavView.IsPaneOpen;
    }

    private async void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.IsSettingsSelected)
        {
            NavFrame.Navigate(typeof(SettingsPage));
            return;
        }

        if (args.SelectedItem is NavigationViewItem item)
        {
            string tag = item.Tag?.ToString();
            if (string.IsNullOrEmpty(tag)) return;

            if (tag == "home")
            {
                NavFrame.Navigate(typeof(HomePage));
            }
            else if (tag == "create_server")
            {
                await ShowCreateServerDialog();
            }
            else if (tag.StartsWith("server_"))
            {
                string serverId = tag.Substring(7);
                var server = _servers.Find(s => s.Id == serverId);
                if (server != null)
                {
                    // Pass the server and client tuple
                    NavFrame.Navigate(typeof(ServerDetailPage), Tuple.Create(server, IpcClient));
                }
            }
        }
    }

    internal async Task ShowCreateServerDialog()
    {
        var dialog = new winui_ui.Dialogs.CreateServerDialog();
        dialog.XamlRoot = this.Content.XamlRoot;
        await dialog.ShowAsync();
        
        // Refresh when closed
        await RefreshServers();
    }

    private void MainWindow_Closed(object sender, WindowEventArgs args)
    {
        IpcClient?.Dispose();
    }
}
