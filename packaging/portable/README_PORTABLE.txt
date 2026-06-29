WeConduct Portable 使用说明

如果此压缩包是从浏览器下载到 Windows 后再解压，Windows 可能会给解压出来
的 exe 和 dll 保留“来自网络”的安全标记。这会导致部分内部运行时组件在首
次启动时被系统拦截，从而出现启动失败。

推荐做法：

1. 在解压前，先右键本 zip 文件，打开“属性”，勾选“解除锁定”，再解压。

2. 如果已经解压且启动失败，请在 PowerShell 中进入 WeConduct 所在目录后执
   行下面的命令，为当前目录下所有文件解除锁定：

   Get-ChildItem '.\\WeConduct' -Recurse -File | Unblock-File

   如果你的目录名不是 WeConduct，请把上面的 '.\\WeConduct' 替换成实际目录。

3. 如果你不希望处理便携包的解除锁定问题，建议优先使用安装版 setup.exe。
