using System;
using System.Collections.Specialized;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

internal static class NativeFileDrag
{
    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out Point point);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 1)
        {
            return 2;
        }

        string path = Path.GetFullPath(args[0]);
        if (!File.Exists(path))
        {
            return 3;
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        Point cursor;
        if (!GetCursorPos(out cursor))
        {
            cursor = Cursor.Position;
        }

        using (Form form = new Form())
        {
            form.FormBorderStyle = FormBorderStyle.None;
            form.ShowInTaskbar = false;
            form.StartPosition = FormStartPosition.Manual;
            form.Bounds = new Rectangle(cursor.X - 2, cursor.Y - 2, 4, 4);
            form.TopMost = true;
            form.Opacity = 0.01;
            form.BackColor = Color.Black;

            form.Shown += delegate
            {
                form.Activate();
                ThreadPool.QueueUserWorkItem(delegate
                {
                    Thread.Sleep(35);
                    form.BeginInvoke((Action)delegate
                    {
                        try
                        {
                            StringCollection files = new StringCollection();
                            files.Add(path);
                            DataObject data = new DataObject();
                            data.SetFileDropList(files);
                            data.SetData(DataFormats.Text, true, path);
                            form.DoDragDrop(data, DragDropEffects.Copy);
                        }
                        finally
                        {
                            form.Close();
                        }
                    });
                });
            };

            Application.Run(form);
        }

        return 0;
    }
}
