"""collector.writers package."""
from collector.writers.comment_writer import CommentWriterWorker
from collector.writers.post_writer import PostWriterWorker

__all__ = ["PostWriterWorker", "CommentWriterWorker"]
