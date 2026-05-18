using System.Text.Json.Serialization;

namespace winui_ui
{
    public class ServerModel
    {
        [JsonPropertyName("id")]
        public string Id { get; set; }

        [JsonPropertyName("name")]
        public string Name { get; set; }

        [JsonPropertyName("mc_version")]
        public string McVersion { get; set; }

        [JsonPropertyName("loader_version")]
        public string LoaderVersion { get; set; }

        [JsonPropertyName("ram_mb")]
        public int RamMb { get; set; }

        [JsonPropertyName("java_version")]
        public int JavaVersion { get; set; }

        [JsonPropertyName("icon_path")]
        public string IconPath { get; set; }

        [JsonPropertyName("created_at")]
        public string CreatedAt { get; set; }

        [JsonPropertyName("path")]
        public string Path { get; set; }

        [JsonPropertyName("autostart")]
        public bool AutoStart { get; set; }
    }
}
