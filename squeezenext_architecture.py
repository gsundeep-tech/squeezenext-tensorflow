from __future__ import absolute_import

import tensorflow as tf

slim = tf.contrib.slim

import tensorflow_extentions as tfe


def squeezenext_block(inputs, filters, stride,height_first_order, groups):
    input_channels = inputs.get_shape().as_list()[-1]
    shortcut = inputs
    # shorcut convolution
    if input_channels != filters or stride != 1:
        shortcut = tfe.grouped_convolution(shortcut, filters, [1, 1], stride=stride,activation_fn=None)
    # input 1x1 reduction conv
    block = tfe.grouped_convolution(inputs, filters / 2, [1, 1], stride=stride, groups=groups)
    block = slim.conv2d(block, block.get_shape().as_list()[-1] / 2, [1, 1])

    # seperable convolutions
    if height_first_order:
        input_channels_seperated = block.get_shape().as_list()[-1]
        block = tfe.grouped_convolution(block, input_channels_seperated * 2, [3, 1], groups=groups)
        block = tfe.grouped_convolution(block, block.get_shape().as_list()[-1], [1, 3], groups=groups)

    else:
        input_channels_seperated = block.get_shape().as_list()[-1]
        block = tfe.grouped_convolution(block, input_channels_seperated * 2, [1, 3], groups=groups)
        block = tfe.grouped_convolution(block, block.get_shape().as_list()[-1], [3, 1], groups=groups)
    # switch order next block
    height_first_order = not height_first_order

    # output convolutions
    block = slim.conv2d(block, block.get_shape().as_list()[-1] * 2, [1, 1],activation_fn=None)
    assert block.get_shape().as_list()[-1] == filters, "Block output channels not equal to number of specified filters"


    return tf.nn.relu(block + shortcut),height_first_order


class SqueezeNext(object):
    """Base class for building the SqueezeNext Model."""

    def __init__(self, num_classes, block_defs, input_def,group_size):
        self.num_classes = num_classes
        self.block_defs = block_defs
        self.input_def = input_def
        self.group_size = group_size


    def __call__(self, inputs, training,height_first_order = True):
        """Add operations to classify a batch of input images.

        Args:
          inputs: A Tensor representing a batch of input images.
          training: A boolean. Set to True to add operations required only when
            training the classifier.

        Returns:
          A logits Tensor with shape [<batch_size>, self.num_classes].
        """
        with tf.variable_scope("squeezenext"):
            # input convolution and pooling
            input_filters, input_kernel,input_stride = self.input_def
            net = slim.conv2d(inputs, input_filters, input_kernel, stride=input_stride,scope="input_conv",padding="VALID")
            net = slim.max_pool2d(net, [3, 3], stride=2)
            # create block based network
            for block_idx,block_def in enumerate(self.block_defs):

                filters,units,stride = block_def
                with tf.variable_scope("block_{}".format(block_idx)):
                    # create seperate units inside a block
                    for unit_idx in range(0,units):
                        with tf.variable_scope("unit_{}".format(unit_idx)):
                            if unit_idx != 0:
                                net,height_first_order = squeezenext_block(net,filters,1,height_first_order,self.group_size)
                                continue

                            else:
                                net,height_first_order = squeezenext_block(net, filters, stride,height_first_order,self.group_size)
            # output conv and pooling
            net = slim.conv2d(net, 128, [1,1],scope="output_conv")
            net = tf.reduce_mean(net,axis=[1,2])
            output = slim.fully_connected(net,self.num_classes,activation_fn=None, biases_initializer=None)
        return output



def squeeze_next_arg_scope(is_training,
                           weight_decay=0.0001):
    batch_norm_params = {
        'is_training': is_training,
        'center': True,
        'scale': True,
        'decay': 0.999,
        'epsilon': 1e-5,
        'fused': True,
    }

    # Set weight_decay for weights in Conv and DepthSepConv layers.
    weights_init = tf.contrib.layers.xavier_initializer()
    regularizer = tf.contrib.layers.l2_regularizer(weight_decay)
    with slim.arg_scope([slim.conv2d,tfe.grouped_convolution],
                        weights_initializer=weights_init,
                        normalizer_fn=slim.batch_norm,
                        normalizer_params=batch_norm_params,
                        biases_initializer=None,
                        weights_regularizer=regularizer):
        with slim.arg_scope([slim.batch_norm], **batch_norm_params) as sc:
            return sc
