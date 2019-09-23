from multiprocessing import Process, Queue
import inspect
import sys
from .exceptions import InferenceError

def run_inference(fn, model, inputs, queue):
    def send_output(output):
        queue.put(dict(data=output))

    def send_error(error):
        queue.put(error.to_response())

    if inspect.isgeneratorfunction(fn):
        g = fn(model, inputs)
        try:
            while True:
                output = next(g)
                send_output(output)
        except StopIteration as err:
            if hasattr(err, 'value') and err.value is not None:
                send_output(err.value)
        except Exception as err:
            error = InferenceError(repr(err))
            send_error(error)
    else:
        try:
            output = fn(model, inputs)
            send_output(output)
        except Exception as err:
            error = InferenceError(repr(err))
            send_error(error)


class InferenceJob(object):
    def __init__(self, command_fn, model, inputs):
        self.model = model
        self.inputs = inputs
        self.queue = Queue()
        self.process = Process(target=run_inference, args=(command_fn, self.model, inputs, self.queue))
        self.data = {}
        self.cancelled = False

    def start(self):
        self.process.start()
    
    def cancel(self):
        self.cancelled = True
        self.process.terminate()

    def refresh_data(self):
        while not self.queue.empty():
            self.data = self.queue.get_nowait()
        return self.data

    def get(self):
        self.refresh_data()
        if self.cancelled:
            return dict(status='CANCELLED', **self.data)
        elif self.process.exitcode is None:
            return dict(status='RUNNING', **self.data)
        elif self.process.exitcode == 0:
            status = 'FAILED' if 'error' in self.data else 'SUCCEEDED'
            return dict(status=status, **self.data)
        else:
            return dict(status='FAILED', error='An unknown error occurred during inference.')