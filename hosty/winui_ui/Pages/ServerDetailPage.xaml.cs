using System;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI;

namespace winui_ui.Pages
{
    public sealed partial class ServerDetailPage : Page
    {
        private ServerModel _server;
        private PythonBackendClient _ipcClient;
        private DispatcherTimer _pollTimer;
        private bool _isLoadingDetails = false;

        public ServerDetailPage()
        {
            InitializeComponent();
            
            _pollTimer = new DispatcherTimer();
            _pollTimer.Interval = TimeSpan.FromSeconds(2);
            _pollTimer.Tick += PollTimer_Tick;
        }

        protected override void OnNavigatedTo(NavigationEventArgs e)
        {
            base.OnNavigatedTo(e);
            
            if (e.Parameter is Tuple<ServerModel, PythonBackendClient> paramsTuple)
            {
                _server = paramsTuple.Item1;
                _ipcClient = paramsTuple.Item2;
                
                // Subscribe to console output and status events
                _ipcClient.ConsoleOutput += OnConsoleOutput;
                _ipcClient.ServerStatusChanged += OnServerStatusChanged;
                
                LoadServerDetails();
                LoadConsoleHistory();
                _pollTimer.Start();
            }
        }

        protected override void OnNavigatedFrom(NavigationEventArgs e)
        {
            base.OnNavigatedFrom(e);
            _pollTimer.Stop();
            
            // Unsubscribe from events
            if (_ipcClient != null)
            {
                _ipcClient.ConsoleOutput -= OnConsoleOutput;
                _ipcClient.ServerStatusChanged -= OnServerStatusChanged;
            }
        }

        private void LoadServerDetails()
        {
            if (_server == null) return;
            _isLoadingDetails = true;

            ServerNameTitle.Text = _server.Name;
            ServerSubtitle.Text = $"Minecraft {_server.McVersion} • {(_server.LoaderVersion != "" ? "Fabric " + _server.LoaderVersion : "Vanilla")}";
            
            RamSlider.Value = _server.RamMb;
            RamValueText.Text = $"{_server.RamMb} MB ({Math.Round(_server.RamMb / 1024.0, 1)} GB)";
            
            // Icon
            if (!string.IsNullOrEmpty(_server.IconPath) && System.IO.File.Exists(_server.IconPath))
            {
                try
                {
                    ServerIcon.Source = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri(_server.IconPath));
                }
                catch {}
            }

            _isLoadingDetails = false;
        }

        private async void LoadConsoleHistory()
        {
            if (_server == null || _ipcClient == null) return;

            try
            {
                var result = await _ipcClient.SendRequestAsync("get_console_log", new { server_id = _server.Id });
                if (result.TryGetProperty("log", out var logProp))
                {
                    foreach (var line in logProp.EnumerateArray())
                    {
                        string text = line.GetString() ?? "";
                        AppendConsoleText(text);
                    }
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading console log: {ex.Message}");
            }
        }

        private void OnConsoleOutput(object? sender, JsonElement data)
        {
            if (_server == null) return;

            string serverId = "";
            string text = "";
            if (data.TryGetProperty("server_id", out var sidProp))
                serverId = sidProp.GetString() ?? "";
            if (data.TryGetProperty("text", out var textProp))
                text = textProp.GetString() ?? "";

            if (serverId != _server.Id) return;

            DispatcherQueue.TryEnqueue(() => AppendConsoleText(text));
        }

        private void OnServerStatusChanged(object? sender, JsonElement data)
        {
            if (_server == null) return;

            string serverId = "";
            string status = "";
            if (data.TryGetProperty("server_id", out var sidProp))
                serverId = sidProp.GetString() ?? "";
            if (data.TryGetProperty("status", out var statusProp))
                status = statusProp.GetString() ?? "";

            if (serverId != _server.Id) return;

            DispatcherQueue.TryEnqueue(() => UpdateStatusUI(status));
        }

        private void UpdateStatusUI(string status)
        {
            switch (status)
            {
                case "running":
                    StatusText.Text = "Running";
                    StatusText.Foreground = new SolidColorBrush(Colors.LimeGreen);
                    StartButton.IsEnabled = false;
                    StopButton.IsEnabled = true;
                    StartButton.Content = "Start";
                    StatsPanel.Visibility = Visibility.Visible;
                    break;
                case "starting":
                    StatusText.Text = "Starting...";
                    StatusText.Foreground = new SolidColorBrush(Colors.Orange);
                    StartButton.IsEnabled = false;
                    StopButton.IsEnabled = false;
                    StartButton.Content = "Starting...";
                    StatsPanel.Visibility = Visibility.Collapsed;
                    break;
                case "stopping":
                    StatusText.Text = "Stopping...";
                    StatusText.Foreground = new SolidColorBrush(Colors.Orange);
                    StartButton.IsEnabled = false;
                    StopButton.IsEnabled = false;
                    break;
                default: // stopped
                    StatusText.Text = "Offline";
                    StatusText.Foreground = new SolidColorBrush(Colors.Gray);
                    StartButton.IsEnabled = true;
                    StopButton.IsEnabled = false;
                    StartButton.Content = "Start";
                    StatsPanel.Visibility = Visibility.Collapsed;
                    CpuText.Text = "—";
                    RamUsageText.Text = "—";
                    PlayerCountText.Text = "—";
                    break;
            }
        }

        private void AppendConsoleText(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            ConsoleText.Text += text;
            
            // Auto-scroll to bottom
            ConsoleScroll.UpdateLayout();
            ConsoleScroll.ChangeView(null, ConsoleScroll.ScrollableHeight, null);
        }

        private async void PollTimer_Tick(object sender, object e)
        {
            if (_server == null || _ipcClient == null) return;

            try
            {
                var result = await _ipcClient.SendRequestAsync("get_runtime_state", new { server_id = _server.Id });
                
                bool isRunning = false;
                if (result.TryGetProperty("is_running", out var runProp))
                    isRunning = runProp.GetBoolean();

                string status = "stopped";
                if (result.TryGetProperty("status", out var statusProp))
                    status = statusProp.GetString() ?? "stopped";

                UpdateStatusUI(status);

                if (isRunning)
                {
                    if (result.TryGetProperty("cpu_percent", out var cpuProp))
                    {
                        CpuText.Text = $"{cpuProp.GetDouble():F1}%";
                    }
                    if (result.TryGetProperty("ram_mb", out var ramProp))
                    {
                        double ramMb = ramProp.GetDouble();
                        if (ramMb >= 1024)
                            RamUsageText.Text = $"{ramMb / 1024.0:F1} GB";
                        else
                            RamUsageText.Text = $"{ramMb:F0} MB";
                    }
                    if (result.TryGetProperty("player_count", out var playerProp) &&
                        result.TryGetProperty("max_players", out var maxProp))
                    {
                        PlayerCountText.Text = $"{playerProp.GetInt32()} / {maxProp.GetInt32()}";
                    }
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error polling server state: {ex.Message}");
            }
        }

        private async void StartButton_Click(object sender, RoutedEventArgs e)
        {
            if (_server == null || _ipcClient == null) return;
            StartButton.IsEnabled = false;
            StartButton.Content = "Starting...";
            ConsoleText.Text = ""; // Clear console on new start
            try
            {
                await _ipcClient.SendRequestAsync("start_server", new { server_id = _server.Id });
            }
            catch (Exception ex)
            {
                var dialog = new ContentDialog
                {
                    Title = "Failed to Start",
                    Content = ex.Message,
                    CloseButtonText = "OK",
                    XamlRoot = this.XamlRoot
                };
                await dialog.ShowAsync();
                StartButton.IsEnabled = true;
                StartButton.Content = "Start";
            }
        }

        private async void StopButton_Click(object sender, RoutedEventArgs e)
        {
            if (_server == null || _ipcClient == null) return;
            StopButton.IsEnabled = false;
            try
            {
                await _ipcClient.SendRequestAsync("stop_server", new { server_id = _server.Id });
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Failed to stop: {ex.Message}");
                StopButton.IsEnabled = true;
            }
        }

        private async void RamSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
        {
            if (_server == null || _ipcClient == null || _isLoadingDetails) return;
            int ram = (int)e.NewValue;
            RamValueText.Text = $"{ram} MB ({Math.Round(ram / 1024.0, 1)} GB)";
            
            // Actually save the RAM change via IPC
            try
            {
                await _ipcClient.SendRequestAsync("update_ram", new { server_id = _server.Id, ram_mb = ram });
                _server.RamMb = ram; // Update local model
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error saving RAM: {ex.Message}");
            }
        }

        private void AutoBackupToggle_Toggled(object sender, RoutedEventArgs e)
        {
            // TODO: wire to preferences via IPC
        }

        private void PlayitToggle_Toggled(object sender, RoutedEventArgs e)
        {
            // TODO: wire to playit via IPC
        }

        private void PlayitSecretBox_PasswordChanged(object sender, RoutedEventArgs e)
        {
            // TODO: wire to playit secret
        }

        private async void ConsoleInputBox_KeyDown(object sender, Microsoft.UI.Xaml.Input.KeyRoutedEventArgs e)
        {
            if (e.Key == Windows.System.VirtualKey.Enter)
            {
                string command = ConsoleInputBox.Text.Trim();
                if (!string.IsNullOrEmpty(command) && _server != null && _ipcClient != null)
                {
                    ConsoleInputBox.Text = "";
                    try
                    {
                        // Echo the command locally
                        AppendConsoleText($"> {command}\n");
                        // Send it to the server process via IPC
                        await _ipcClient.SendRequestAsync("send_command", new { server_id = _server.Id, command = command });
                    }
                    catch (Exception ex)
                    {
                        AppendConsoleText($"[Hosty] Error: {ex.Message}\n");
                    }
                }
            }
        }
    }
}
