using System;
using System.IO;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

// Loads Terraria's XNB textures through the real XNA content pipeline and writes PNGs.
class Exporter : Game
{
    GraphicsDeviceManager gdm;
    string contentRoot, outDir, listFile;

    public Exporter(string root, string outDir, string listFile)
    {
        gdm = new GraphicsDeviceManager(this);
        gdm.GraphicsProfile = GraphicsProfile.Reach;
        gdm.PreferredBackBufferWidth = 64;
        gdm.PreferredBackBufferHeight = 64;
        contentRoot = root; this.outDir = outDir; this.listFile = listFile;
        Content.RootDirectory = root;
    }

    protected override void LoadContent()
    {
        int ok = 0, bad = 0;
        foreach (var raw in File.ReadAllLines(listFile))
        {
            var name = raw.Trim();
            if (name.Length == 0) continue;
            try
            {
                var tex = Content.Load<Texture2D>(name);
                var dst = Path.Combine(outDir, name.Replace('/', '_').Replace('\\', '_') + ".png");
                using (var fs = File.Create(dst)) tex.SaveAsPng(fs, tex.Width, tex.Height);
                ok++;
            }
            catch (Exception e) { Console.WriteLine("FAIL " + name + ": " + e.Message); bad++; }
        }
        Console.WriteLine("exported " + ok + " failed " + bad);
        Exit();
    }

    [STAThread]
    static void Main(string[] a)
    {
        Directory.CreateDirectory(a[1]);
        using (var g = new Exporter(a[0], a[1], a[2])) g.Run();
    }
}
