using Microsoft.UI.Xaml.Controls;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace winui_ui.Pages;

public sealed partial class HomePage : Page
{
    public HomePage()
    {
        InitializeComponent();
        CreateServerButton.Click += CreateServerButton_Click;
    }

    private async void CreateServerButton_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        if (App.MainWindow != null)
        {
            await App.MainWindow.ShowCreateServerDialog();
        }
    }
}
