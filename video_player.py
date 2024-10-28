import logging
import platform
import sys

import vlc
from PySide6.QtCore import QEvent, QMetaObject, QPoint, Qt, QTimer, Slot
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFrame, QMainWindow, QProgressBar, QVBoxLayout

logging.basicConfig(level=logging.ERROR)


class VLCLogger:
    def __init__(self):
        self.latest_error = ""

    def log(self, message):
        self.latest_error = message
        logging.error(f"VLC Error: {message}")

    def get_latest_error(self):
        return self.latest_error


class VideoPlayer(QMainWindow):
	@@ -32,7 +47,7 @@ def __init__(self, config_manager, *args, **kwargs):
        self.mainFrame = QFrame()
        self.setCentralWidget(self.mainFrame)
        self.setWindowTitle("QiTV Player")
        t_lay_parent = QVBoxLayout()
        t_lay_parent.setContentsMargins(0, 0, 0, 0)

        self.video_frame = QFrame()
	@@ -42,13 +57,23 @@ def __init__(self, config_manager, *args, **kwargs):

        # Custom user-agent string
        user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
        self.vlc_logger = VLCLogger()

        # Initialize VLC instance
        self.instance = vlc.Instance(
            ["--video-on-top", f"--http-user-agent={user_agent}"]
        )  # vlc.Instance(["--verbose=2"])  # Enable verbose logging

        self.media_player = self.instance.media_player_new()
        self.media_player.video_set_mouse_input(False)
        self.media_player.video_set_key_input(False)

        # Set up event manager for logging
        self.event_manager = self.media_player.event_manager()
        self.event_manager.event_attach(
            vlc.EventType.MediaPlayerEncounteredError, self.on_vlc_error
        )

        if sys.platform.startswith("linux"):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
	@@ -61,43 +86,66 @@ def __init__(self, config_manager, *args, **kwargs):

        self.resize_corner = None

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1000)  # Use 1000 steps for smoother updates
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("00:00 / 00:00")
        self.mainFrame.layout().addWidget(self.progress_bar)

        self.update_timer = QTimer(self)
        self.update_timer.setInterval(100)  # Update every 100ms
        self.update_timer.timeout.connect(self.update_progress)

        self.progress_bar.mousePressEvent = self.seek_video

        self.click_position = None
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.handle_click)

    def seek_video(self, event):
        if self.media_player.is_playing():
            width = self.progress_bar.width()
            click_position = event.position().x()
            seek_position = click_position / width
            self.media_player.set_position(seek_position)

    def format_time(self, milliseconds):
        seconds = int(milliseconds / 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    def update_progress(self):
        state = self.media_player.get_state()
        if state == vlc.State.Playing:
            current_time = self.media_player.get_time()
            total_time = self.media.get_duration()

            if total_time > 0:
                formatted_current = self.format_time(current_time)
                formatted_total = self.format_time(total_time)
                self.progress_bar.setFormat(f"{formatted_current} / {formatted_total}")
                self.progress_bar.setValue(int(current_time * 1000 / total_time))
            else:
                self.progress_bar.setFormat("Live")
                self.progress_bar.setValue(0)
        elif state == vlc.State.Error:
            self.handle_error("Playback error")
        elif state == vlc.State.Ended:
            self.progress_bar.setFormat("Playback ended")
            self.progress_bar.setValue(1000)  # Set to 100%
        elif state == vlc.State.Opening:
            self.progress_bar.setFormat("Opening...")
            self.progress_bar.setValue(0)
        elif state == vlc.State.Buffering:
            self.progress_bar.setFormat("Buffering...")
            self.progress_bar.setValue(0)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
	@@ -173,12 +221,33 @@ def play_video(self, video_url):

        self.media = self.instance.media_new(video_url)
        self.media_player.set_media(self.media)

        events = self.media_player.event_manager()
        events.event_attach(
            vlc.EventType.MediaPlayerLengthChanged, self.on_media_length_changed
        )
        self.media.parse_with_options(1, 0)

        play_result = self.media_player.play()
        if play_result == -1:
            self.handle_error("Failed to start playback")
        else:
            self.adjust_aspect_ratio()
            self.show()
            QTimer.singleShot(5000, self.check_playback_status)

    def check_playback_status(self):
        if not self.media_player.is_playing():
            media_state = self.media.get_state()
            if media_state == vlc.State.Error:
                self.handle_error("Playback error")
            else:
                self.handle_error("Failed to start playback")

    def stop_video(self):
        self.media_player.stop()
        self.progress_bar.setVisible(False)
        self.update_timer.stop()

    def toggle_mute(self):
        state = self.media_player.audio_get_mute()
	@@ -212,6 +281,16 @@ def toggle_pip_mode(self):
        QGuiApplication.restoreOverrideCursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_position = event.globalPos()
            self.click_timer.start(
                200
            )  # Wait for 200ms to determine if it's a click or drag

        elif event.button() == Qt.RightButton:
            self.toggle_pip_mode()
            return

        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.resizing = False
	@@ -246,6 +325,12 @@ def mousePressEvent(self, event):
            event.accept()

    def mouseMoveEvent(self, event):
        if (
            self.click_timer.isActive()
            and (event.globalPos() - self.click_position).manhattanLength() > 3
        ):
            self.click_timer.stop()  # Cancel the click timer if the mouse has moved

        if self.resizing:
            delta = event.globalPos() - self.drag_position
            new_width, new_height = self.start_size.width(), self.start_size.height()
	@@ -272,10 +357,18 @@ def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.click_timer.isActive():
            self.click_timer.stop()
            self.handle_click()

        self.dragging = False
        self.resizing = False
        self.resize_corner = None

    def handle_click(self):
        # This method is called when a single click is detected
        self.toggle_play_pause()

    def resize_to_aspect_ratio(self):
        width = self.width()
        height = int(width / self.aspect_ratio)
	@@ -310,3 +403,37 @@ def adjust_aspect_ratio(self):
            width, height = video_size
            if width > 0 and height > 0:
                self.aspect_ratio = width / height

    def on_media_length_changed(self, event):
        QMetaObject.invokeMethod(self, "media_length_changed", Qt.QueuedConnection)

    @Slot()
    def media_length_changed(self):
        duration = self.media.get_duration()
        if duration > 0:  # VOD content
            self.progress_bar.setVisible(True)
            self.progress_bar.setFormat("00:00 / " + self.format_time(duration))
            self.update_timer.start()
        else:  # Live content
            self.progress_bar.setVisible(False)  # Hide the progress bar
            self.progress_bar.setFormat("Live")
            # self.update_timer.start()

    def on_vlc_error(self, event):
        # We don't use event data here, just log that an error occurred
        self.vlc_logger.log("An error occurred during playback")
        QMetaObject.invokeMethod(self, "media_error_occurred", Qt.QueuedConnection)

    @Slot()
    def media_error_occurred(self):
        self.handle_error("Playback error occurred")

    def handle_error(self, error_message):
        vlc_error = self.vlc_logger.get_latest_error()
        if vlc_error:
            error_message += f": {vlc_error}"
        logging.error(f"VLC Error: {error_message}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat(f"Error: {error_message}")
        self.progress_bar.setValue(0)
        self.update_timer.stop()
