import copy

from ccxtbt.dash.dash__specifications import dash_user_input__dict_template

thread_queue__dict_template = copy.deepcopy(dash_user_input__dict_template)
thread_queue__dict_template.update(dict(
    # Thread and Queue Params
    thread=None,
    # Thread name defined by Python library. DO NOT rename this attribute.
    name=None,
    thread_limiter=None,
    thread_barrier=None,

    # Parent to children FIFO queues
    p2c__outbound_fifo_queue=None,
    p2c__inbound_fifo_queue=None,

    # Children to parent FIFO queue
    c2p__outbound_fifo_queue=None,
    c2p__inbound_fifo_queue=None,

    # Hub to node FIFO queue
    h2n__outbound_fifo_queue=None,
    h2n__inbound_fifo_queue=None,

    perform_loopback=None,
))
