# MT_HairTools

Bộ công cụ Python cho Maya 2023 (hair card). Code chạy trong Maya, dùng `maya.cmds` và `maya.api.OpenMaya`.

# Thiết lập VS Code để Pylance không báo lỗi giả với thư viện Maya

Khi người dùng nói VS Code báo lỗi giả với `maya.cmds`, `maya.api.OpenMaya`..., hoặc khi dựng môi trường trên máy mới, làm theo các bước dưới. Cấu hình đặt ở **setting chung (User) của VS Code**, không đặt trong `.vscode/` của dự án, để mọi dự án Maya đều dùng được.

## Nguyên nhân các lỗi giả

| Lỗi hiện trong VS Code | Nguyên nhân |
|---|---|
| `Import "maya.cmds" could not be resolved` | Python mà Pylance dùng không biết thư viện Maya nằm ở đâu. |
| `"button" is not a known attribute of module "maya.cmds"` | `maya.cmds` chỉ được nạp hàm khi chạy trong Maya, file `.py` thật trống. |
| `"MGlobal" is not a known attribute of module "maya.api.OpenMaya"` | `maya.api.OpenMaya` viết bằng C++ (`.pyd`), Pylance không đọc được. |
| `No parameter named "label"` (hàng trăm lỗi) | Bộ stub `mayaSDK` của extension MayaPy (`fxtd-odyssey.mayapy`) chỉ khai báo cờ ngắn (`q=1`...). Không dùng bộ stub này. |

Người dùng để `"python.analysis.typeCheckingMode": "standard"`, nên stub sai sẽ bị báo lỗi. Không hạ chế độ kiểm tra và không tắt các rule như `reportAttributeAccessIssue` để che lỗi, vì như vậy sẽ che luôn lỗi thật.

## Các bước thực hiện

1. **Tìm mayapy** của bản Maya đang cài, thường là `C:\Program Files\Autodesk\Maya<phiên bản>\bin\mayapy.exe`. Máy khác có thể dùng phiên bản Maya hoặc tên user Windows khác, nên phải kiểm tra lại, không chép đường dẫn trong tài liệu này.

2. **Sinh stub** bằng script trong repo, [Tools/MayaStubs/gen_maya_stubs.py](Tools/MayaStubs/gen_maya_stubs.py). Script đọc trực tiếp từ Maya, không tải gì từ Internet:
   ```bash
   PYTHONIOENCODING=utf-8 "/c/Program Files/Autodesk/Maya2023/bin/mayapy.exe" Tools/MayaStubs/gen_maya_stubs.py "C:/Users/<user>/maya-typings"
   ```
   - Bắt buộc có `PYTHONIOENCODING=utf-8`, nếu không mayapy lỗi `UnicodeEncodeError` khi in tiếng Việt.
   - Kết quả: `maya/cmds/__init__.pyi` (khoảng 4.700 hàm, có đủ tên cờ dài và ngắn), `maya/mel/__init__.pyi`, `maya/api/__init__.pyi`, `maya/api/OpenMaya*.pyi`. Ở Maya 2023, `OpenMayaFX` không có trong `maya.api`, script tự bỏ qua.
   - Phải có `maya/api/__init__.pyi`. Thiếu file này thì Pylance vẫn dùng module thật và vẫn báo lỗi `MGlobal`.
   - Không cài gói `maya-stubs` từ PyPI: lần trước hệ thống quyền đã chặn việc tải code từ ngoài, còn stub tự sinh thì khớp đúng bản Maya đang dùng.

3. **Sửa setting chung của VS Code** trong `%APPDATA%\Code\User\settings.json`. Đọc file trước khi sửa và giữ nguyên các setting khác:
   ```json
   "python.analysis.extraPaths": [
       "C:\\Program Files\\Autodesk\\Maya2023\\Python\\Lib\\site-packages"
   ],
   "python.analysis.stubPath": "C:\\Users\\<user>\\maya-typings",
   ```
   - `extraPaths` để resolve được các module Maya chưa có stub (`maya.OpenMaya` API 1.0, `maya.utils`, `PySide2`...).
   - Nếu `extraPaths` cũ đang trỏ tới `...\fxtd-odyssey.mayapy-*\mayaSDK`, thay hẳn bằng đường dẫn trên. Đừng giữ song song.
   - Nếu workspace có `.vscode/settings.json` chứa `extraPaths` hoặc `stubPath` riêng, nó sẽ ghi đè setting chung. Hỏi người dùng trước khi xóa.

4. **Cho Pylance nạp lại.** Pylance không theo dõi thư mục `stubPath`, nên khi thêm hoặc sửa file stub thì phải nạp lại bằng một trong hai cách:
   - Bảo người dùng chạy lệnh `Developer: Reload Window`.
   - Hoặc tạm đổi `stubPath` sang một đường dẫn khác rồi đổi về lại. Chỉ đổi dấu `\` thành `/` thì không đủ, vì đường dẫn sau khi chuẩn hóa vẫn như cũ.

5. **Kiểm tra** bằng tool `getDiagnostics` của VS Code (hoặc panel Problems). Ngay sau khi đổi setting, kết quả có thể tạm trống trong lúc Pylance phân tích lại, nên gọi thêm một lần nữa. Kết quả đúng: các file trong `SourceCode/` không còn lỗi `reportAttributeAccessIssue` hay `reportMissingImports` liên quan tới Maya. Lỗi còn lại, như `"om" is not defined`, là lỗi thật trong code: báo cho người dùng chứ không che đi.

## Khi nâng cấp Maya

Chạy lại bước 2 bằng `mayapy.exe` của bản mới, rồi sửa đường dẫn `Maya2023` trong `extraPaths` ở bước 3.
