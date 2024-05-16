# maya_umbrella_scanner
A portable version for maya umbrella scanner.

# 安装
从 [release](https://github.com/loonghao/maya_umbrella_scanner/releases) 页面下载安装包，然后解压缩并使用。

# 用法
## 病毒扫描
使用 --path 参数指定要扫描的路径，程序将递归扫描路径下所有的 ma 或 mb 文件。
```shell
maya_umbrella --path <your/sreach/path>
```
例如，要扫描 c:/test 文件夹下的所有 ma 或 mb 文件，感染文件列表将保存在 %temp%/maya-umbrella/infected.txt 中。
```shell
maya_umbrella --path c:/test
```
## 自动杀毒
使用 --path 参数指定要扫描的路径，程序将递归扫描路径下所有的 ma 或 mb 文件。
使用 --maya-version 参数指定本地安装的 Maya 版本，例如 2019。需要启动本地安装的 Maya 的 standalone 版本进行杀毒。
```shell
maya_umbrella --path <your/sreach/path> --maya-version <maya version>
```
