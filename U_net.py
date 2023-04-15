{
  "nbformat": 4,
  "nbformat_minor": 0,
  "metadata": {
    "colab": {
      "provenance": [],
      "authorship_tag": "ABX9TyP8e4bpalwLxWjLPj2q4KBl"
    },
    "kernelspec": {
      "name": "python3",
      "display_name": "Python 3"
    },
    "language_info": {
      "name": "python"
    },
    "gpuClass": "standard"
  },
  "cells": [
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {
        "id": "Uh3vBAtjIDkP",
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "outputId": "38596bc5-9bd3-43d8-b077-fe78659139ff"
      },
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Mounted at /content/drive/\n"
          ]
        }
      ],
      "source": [
        "from google.colab import drive\n",
        "drive.mount('/content/drive/')\n",
        "\n",
        "import os\n",
        "import tensorflow\n",
        "from tensorflow.keras.layers import Conv2D,\\\n",
        "MaxPool2D, Conv2DTranspose, Input, Activation,\\\n",
        "Concatenate, CenterCrop\n",
        "from tensorflow.keras import Model\n",
        "from tensorflow.keras.initializers import HeNormal\n",
        "from tensorflow.keras.optimizers import schedules, Adam\n",
        "from tensorflow.keras.losses import SparseCategoricalCrossentropy\n",
        "from tensorflow.keras.callbacks import TensorBoard, CSVLogger\n",
        "from tensorflow.keras.utils import plot_model\n",
        "import tensorflow_datasets as tfds\n",
        "import matplotlib.pyplot as plt\n",
        "import time\n",
        "import json"
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "'''\n",
        "    U-NET CONFIGURATION\n",
        "'''\n",
        "def configuration():\n",
        "    ''' Get configuration. '''\n",
        "\n",
        "    return dict(\n",
        "        data_train_prc = 15,\n",
        "        data_val_prc = 20,\n",
        "        data_test_prc = 25,\n",
        "        num_filters_start = 64,\n",
        "        num_unet_blocks = 3,\n",
        "        num_filters_end = 3,\n",
        "        input_width = 100,\n",
        "        input_height = 100,\n",
        "        mask_width = 60,\n",
        "        mask_height = 60,\n",
        "        input_dim = 3,\n",
        "        optimizer = Adam,\n",
        "        loss = SparseCategoricalCrossentropy,\n",
        "        initializer = HeNormal(),\n",
        "        buffer_size = 10,\n",
        "        metrics = ['accuracy'],\n",
        "        dataset_path = \"/content/drive/My Drive/data\",\n",
        "        class_weights = tensorflow.constant([1.0, 1.0, 2.0]),\n",
        "        validation_sub_splits = 5,\n",
        "        lr_schedule_percentages = [0.2, 0.5, 0.8],\n",
        "        lr_schedule_values = [3e-4, 1e-4, 1e-5, 1e-6],\n",
        "        lr_schedule_class = schedules.PiecewiseConstantDecay\n",
        "    )"
      ],
      "metadata": {
        "id": "uITV2Fy8INWE"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "'''\n",
        "    U-NET BUILDING BLOCKS\n",
        "'''\n",
        "\n",
        "def conv_block(x, filters, last_block):\n",
        "    '''\n",
        "        U-Net convolutional block.\n",
        "        Used for downsampling in the contracting path.\n",
        "    '''\n",
        "    config = configuration()\n",
        "\n",
        "    # First Conv segment\n",
        "    x = Conv2D(filters, (3, 3),\\\n",
        "        kernel_initializer=config.get(\"initializer\"))(x)\n",
        "    x = Activation(\"relu\")(x)\n",
        "\n",
        "    # Second Conv segment\n",
        "    x = Conv2D(filters, (3, 3),\\\n",
        "        kernel_initializer=config.get(\"initializer\"))(x)\n",
        "    x = Activation(\"relu\")(x)\n",
        "\n",
        "    # Keep Conv output for skip input\n",
        "    skip_input = x\n",
        "\n",
        "    # Apply pooling if not last block\n",
        "    if not last_block:\n",
        "        x = MaxPool2D((2, 2), strides=(2,2))(x)\n",
        "\n",
        "    return x, skip_input"
      ],
      "metadata": {
        "id": "WRs3ITGOIPlK"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def contracting_path(x):\n",
        "    '''\n",
        "        U-Net contracting path.\n",
        "        Initializes multiple convolutional blocks for \n",
        "        downsampling.\n",
        "    '''\n",
        "    config = configuration()\n",
        "\n",
        "    # Compute the number of feature map filters per block\n",
        "    num_filters = [compute_number_of_filters(index)\\\n",
        "            for index in range(config.get(\"num_unet_blocks\"))]\n",
        "\n",
        "    # Create container for the skip input Tensors\n",
        "    skip_inputs = []\n",
        "\n",
        "    # Pass input x through all convolutional blocks and\n",
        "    # add skip input Tensor to skip_inputs if not last block\n",
        "    for index, block_num_filters in enumerate(num_filters):\n",
        "\n",
        "        last_block = index == len(num_filters)-1\n",
        "        x, skip_input = conv_block(x, block_num_filters,\\\n",
        "            last_block)\n",
        "\n",
        "        if not last_block:\n",
        "            skip_inputs.append(skip_input)\n",
        "\n",
        "    return x, skip_inputs"
      ],
      "metadata": {
        "id": "NPVLIe3-IRpq"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def upconv_block(x, filters, skip_input, last_block = False):\n",
        "    '''\n",
        "        U-Net upsampling block.\n",
        "        Used for upsampling in the expansive path.\n",
        "    '''\n",
        "    config = configuration()\n",
        "\n",
        "    # Perform upsampling\n",
        "    x = Conv2DTranspose(filters//2, (2, 2), strides=(2, 2),\\\n",
        "        kernel_initializer=config.get(\"initializer\"))(x)\n",
        "    shp = x.shape\n",
        "\n",
        "    # Crop the skip input, keep the center\n",
        "    cropped_skip_input = CenterCrop(height = x.shape[1],\\\n",
        "        width = x.shape[2])(skip_input)\n",
        "\n",
        "    # Concatenate skip input with x\n",
        "    concat_input = Concatenate(axis=-1)([cropped_skip_input, x])\n",
        "\n",
        "    # First Conv segment\n",
        "    x = Conv2D(filters//2, (3, 3),\n",
        "        kernel_initializer=config.get(\"initializer\"))(concat_input)\n",
        "    x = Activation(\"relu\")(x)\n",
        "\n",
        "    # Second Conv segment\n",
        "    x = Conv2D(filters//2, (3, 3),\n",
        "        kernel_initializer=config.get(\"initializer\"))(x)\n",
        "    x = Activation(\"relu\")(x)\n",
        "\n",
        "    # Prepare output if last block\n",
        "    if last_block:\n",
        "        x = Conv2D(config.get(\"num_filters_end\"), (1, 1),\n",
        "            kernel_initializer=config.get(\"initializer\"))(x)\n",
        "\n",
        "    return x"
      ],
      "metadata": {
        "id": "i4yXCvP1IUER"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def expansive_path(x, skip_inputs):\n",
        "    '''\n",
        "        U-Net expansive path.\n",
        "        Initializes multiple upsampling blocks for upsampling.\n",
        "    '''\n",
        "    num_filters = [compute_number_of_filters(index)\\\n",
        "            for index in range(configuration()\\\n",
        "                .get(\"num_unet_blocks\")-1, 0, -1)]\n",
        "\n",
        "    skip_max_index = len(skip_inputs) - 1\n",
        "\n",
        "    for index, block_num_filters in enumerate(num_filters):\n",
        "        skip_index = skip_max_index - index\n",
        "        last_block = index == len(num_filters)-1\n",
        "        x = upconv_block(x, block_num_filters,\\\n",
        "            skip_inputs[skip_index], last_block)\n",
        "\n",
        "    return x"
      ],
      "metadata": {
        "id": "yPcTX5C0IV_x"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def build_unet():\n",
        "    ''' Construct U-Net. '''\n",
        "    config = configuration()\n",
        "    input_shape = (config.get(\"input_height\"),\\\n",
        "        config.get(\"input_width\"), config.get(\"input_dim\"))\n",
        "\n",
        "    # Construct input layer\n",
        "    input_data = Input(shape=input_shape)\n",
        "\n",
        "    # Construct Contracting path\n",
        "    contracted_data, skip_inputs = contracting_path(input_data)\n",
        "\n",
        "    # Construct Expansive path\n",
        "    expanded_data = expansive_path(contracted_data, skip_inputs)\n",
        "\n",
        "    # Define model\n",
        "    model = Model(input_data, expanded_data, name=\"U-Net\")\n",
        "\n",
        "    return model"
      ],
      "metadata": {
        "id": "yf9LKGFWIXxm"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def compute_number_of_filters(block_number):\n",
        "    '''\n",
        "        Compute the number of filters for a specific\n",
        "        U-Net block given its position in the contracting path.\n",
        "    '''\n",
        "    return configuration().get(\"num_filters_start\") * (2 ** block_number)"
      ],
      "metadata": {
        "id": "WdHpAGo3IZov"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "'''\n",
        "    U-NET TRAINING PROCESS BUILDING BLOCKS\n",
        "'''\n",
        "\n",
        "def init_model(steps_per_epoch, num_epochs):\n",
        "    '''\n",
        "        Initialize a U-Net model.\n",
        "    '''\n",
        "    config = configuration()\n",
        "    model = build_unet()\n",
        "\n",
        "    # Retrieve compilation input\n",
        "    loss_init = config.get(\"loss\")(from_logits=True)\n",
        "    metrics = config.get(\"metrics\")\n",
        "\n",
        "    # Construct LR schedule\n",
        "    boundaries = [int(num_epochs * percentage * steps_per_epoch)\\\n",
        "        for percentage in config.get(\"lr_schedule_percentages\")]\n",
        "    lr_schedule = config.get(\"lr_schedule_class\")(boundaries, config.get(\"lr_schedule_values\"))\n",
        "\n",
        "    # Init optimizer\n",
        "    optimizer_init = config.get(\"optimizer\")(learning_rate = lr_schedule)\n",
        "\n",
        "    # Compile the model\n",
        "    model.compile(loss=loss_init, optimizer=optimizer_init, metrics=metrics)\n",
        "\n",
        "    # Plot the model\n",
        "    plot_model(model, to_file=\"unet.png\")\n",
        "\n",
        "    # Print model summary\n",
        "    model.summary()\n",
        "\n",
        "    return model"
      ],
      "metadata": {
        "id": "daQtHG0JIbUf"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def load_dataset():\n",
        "    '''\tReturn dataset with info. '''\n",
        "    config = configuration()\n",
        "\n",
        "    # Retrieve percentages\n",
        "    train = config.get(\"data_train_prc\")\n",
        "    val = config.get(\"data_val_prc\")\n",
        "    test = config.get(\"data_test_prc\")\n",
        "\n",
        "    # Redefine splits over full dataset\n",
        "    splits = [f'train[:{train}%]+test[:{train}%]',\\\n",
        "        f'train[{train}%:{val}%]+test[{train}%:{val}%]',\\\n",
        "        f'train[{val}%:{test}%]+test[{val}%:{test}%]']\n",
        "\n",
        "    # Return data\n",
        "    return tfds.load('oxford_iiit_pet:3.*.*', split=splits, data_dir=configuration()\\\n",
        "        .get(\"dataset_path\"), with_info=True) "
      ],
      "metadata": {
        "id": "vtUiUwIqIdct"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def normalize_sample(input_image, input_mask):\n",
        "    ''' Normalize input image and mask class. '''\n",
        "    # Cast image to float32 and divide by 255\n",
        "    input_image = tensorflow.cast(input_image, tensorflow.float32) / 255.0\n",
        "\n",
        "  # Bring classes into range [0, 2]\n",
        "    input_mask -= 1\n",
        "\n",
        "    return input_image, input_mask"
      ],
      "metadata": {
        "id": "XVYqPTE2Ifbc"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def preprocess_sample(data_sample):\n",
        "    ''' Resize and normalize dataset samples. '''\n",
        "    config = configuration()\n",
        "\n",
        "    # Resize image\n",
        "    input_image = tensorflow.image.resize(data_sample['image'],\\\n",
        "    (config.get(\"input_width\"), config.get(\"input_height\")))\n",
        "\n",
        "  # Resize mask\n",
        "    input_mask = tensorflow.image.resize(data_sample['segmentation_mask'],\\\n",
        "    (config.get(\"mask_width\"), config.get(\"mask_height\")))\n",
        "\n",
        "  # Normalize input image and mask\n",
        "    input_image, input_mask = normalize_sample(input_image, input_mask)\n",
        "\n",
        "    return input_image, input_mask"
      ],
      "metadata": {
        "id": "dWtl8-TEIg9Y"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def data_augmentation(inputs, labels):\n",
        "    ''' Perform data augmentation. '''\n",
        "    # Use the same seed for deterministic randomness over both inputs and labels.\n",
        "    seed = 36\n",
        "\n",
        "  # Feed data through layers\n",
        "    inputs = tensorflow.image.random_flip_left_right(inputs, seed=seed)\n",
        "    inputs = tensorflow.image.random_flip_up_down(inputs, seed=seed)\n",
        "    labels = tensorflow.image.random_flip_left_right(labels, seed=seed)\n",
        "    labels = tensorflow.image.random_flip_up_down(labels, seed=seed)\n",
        "\n",
        "    return inputs, labels"
      ],
      "metadata": {
        "id": "rC_uyvVDIi4q"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def compute_sample_weights(image, mask):\n",
        "    ''' Compute sample weights for the image given class. '''\n",
        "    # Compute relative weight of class\n",
        "    class_weights = configuration().get(\"class_weights\")\n",
        "    class_weights = class_weights/tensorflow.reduce_sum(class_weights)\n",
        "\n",
        "  # Compute same-shaped Tensor as mask with sample weights per\n",
        "  # mask element. \n",
        "    sample_weights = tensorflow.gather(class_weights,indices=\\\n",
        "    tensorflow.cast(mask, tensorflow.int32))\n",
        "\n",
        "    return image, mask, sample_weights"
      ],
      "metadata": {
        "id": "-X0Hc__VIkYq"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def preprocess_dataset(data, dataset_type, dataset_info, batch_size):\n",
        "    ''' Fully preprocess dataset given dataset type. '''\n",
        "    config = configuration()\n",
        "    buffer_size = config.get(\"buffer_size\")\n",
        "\n",
        "    # Preprocess data given dataset type.\n",
        "    if dataset_type == \"train\" or dataset_type == \"val\":\n",
        "        # 1. Perform preprocessing\n",
        "        # 2. Cache dataset for improved performance\n",
        "        # 3. Shuffle dataset\n",
        "        # 4. Generate batches\n",
        "        # 5. Repeat\n",
        "        # 6. Perform data augmentation\n",
        "        # 7. Add sample weights\n",
        "        # 8. Prefetch new data before it being necessary.\n",
        "        return (data\n",
        "                    .map(preprocess_sample)\n",
        "                    .cache()\n",
        "                    .shuffle(buffer_size)\n",
        "                    .batch(batch_size)\n",
        "                    .repeat()\n",
        "                    .map(data_augmentation)\n",
        "                    .map(compute_sample_weights)\n",
        "                    .prefetch(buffer_size=tensorflow.data.AUTOTUNE))\n",
        "    else:\n",
        "        # 1. Perform preprocessing\n",
        "        # 2. Generate batches\n",
        "        return (data\n",
        "                        .map(preprocess_sample)\n",
        "                        .batch(batch_size))"
      ],
      "metadata": {
        "id": "Ig0U7DcIIl-F"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def training_callbacks():\n",
        "    ''' Retrieve initialized callbacks for model.fit '''\n",
        "    return [\n",
        "        TensorBoard(\n",
        "          log_dir=os.path.join(os.getcwd(), \"unet_logs\"),\n",
        "          histogram_freq=1,\n",
        "          write_images=True\n",
        "        )\n",
        "    ]"
      ],
      "metadata": {
        "id": "ppKgWfQ5InoQ"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def probs_to_mask(probs):\n",
        "    ''' Convert Softmax output into mask. '''\n",
        "    pred_mask = tensorflow.argmax(probs, axis=2)\n",
        "    return pred_mask"
      ],
      "metadata": {
        "id": "PgXrFUPLIpLL"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "def generate_plot(img_input, mask_truth, mask_probs):\n",
        "    ''' Generate a plot of input, truthy mask and probability mask. '''\n",
        "    fig, axs = plt.subplots(1, 4)\n",
        "    fig.set_size_inches(16, 6)\n",
        "\n",
        "    # Plot the input image\n",
        "    axs[0].imshow(img_input)\n",
        "    axs[0].set_title(\"Input image\")\n",
        "\n",
        "    # Plot the truthy mask\n",
        "    axs[1].imshow(mask_truth)\n",
        "    axs[1].set_title(\"True mask\")\n",
        "\n",
        "    # Plot the predicted mask\n",
        "    predicted_mask = probs_to_mask(mask_probs)\n",
        "    axs[2].imshow(predicted_mask)\n",
        "    axs[2].set_title(\"Predicted mask\")\n",
        "\n",
        "    # Plot the overlay\n",
        "    config = configuration()\n",
        "    img_input_resized = tensorflow.image.resize(img_input, (config.get(\"mask_width\"), config.get(\"mask_height\")))\n",
        "    axs[3].imshow(img_input_resized)\n",
        "    axs[3].imshow(predicted_mask, alpha=0.5)\n",
        "    axs[3].set_title(\"Overlay\")\n",
        "\n",
        "    # Show the plot\n",
        "    plt.show()"
      ],
      "metadata": {
        "id": "T6dSxbV5Iqm2"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "batch_size = 4\n",
        "num_epochs = 2\n",
        "\n",
        "print(\"Batch size: \", batch_size, \"\\nNum_epochs: \", num_epochs)"
      ],
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "K7rF7OXGwkPu",
        "outputId": "cd650c0d-f540-4b35-a114-2e07b3bd6028"
      },
      "execution_count": null,
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Batch size:  4 \n",
            "Num_epochs:  2\n"
          ]
        }
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "#def main():\n",
        "''' Run full training procedure. '''\n",
        "\n",
        "# Load config\n",
        "config = configuration()\n",
        "#batch_size = config.get(\"batch_size\")\n",
        "validation_sub_splits = config.get(\"validation_sub_splits\")\n",
        "#num_epochs = config.get(\"num_epochs\")\n",
        "\n",
        "# Load data\n",
        "(training_data, validation_data, testing_data), info = load_dataset()\n",
        "\n",
        "# Make training data ready for model.fit and model.evaluate\n",
        "train_batches = preprocess_dataset(training_data, \"train\", info, batch_size)\n",
        "val_batches = preprocess_dataset(validation_data, \"val\", info, batch_size)\n",
        "test_batches = preprocess_dataset(testing_data, \"test\", info, batch_size)\n",
        "\n",
        "# Compute data-dependent variables\n",
        "train_num_samples = tensorflow.data.experimental.cardinality(training_data).numpy()\n",
        "val_num_samples = tensorflow.data.experimental.cardinality(validation_data).numpy()\n",
        "steps_per_epoch = train_num_samples // batch_size\n",
        "val_steps_per_epoch = val_num_samples // batch_size // validation_sub_splits\n",
        "\n",
        "# Initialize model\n",
        "model = init_model(steps_per_epoch, num_epochs)\n",
        "\n",
        "# Train the model\t\n",
        "start_train = time.time()\n",
        "history = model.fit(train_batches, epochs=num_epochs, batch_size=batch_size,\\\n",
        "    steps_per_epoch=steps_per_epoch, verbose=1,\n",
        "    validation_steps=val_steps_per_epoch, callbacks=training_callbacks(),\\\n",
        "    validation_data=val_batches)\n",
        "end_train = time.time()\n",
        "\n",
        "time_train = int(end_train-start_train)\n",
        "av_time_epoch = time_train/num_epochs\n",
        "av_time_img = av_time_epoch/275 #количество изображений в эпохе (надо переделать проценты)\n",
        "\n",
        "print(\"The time of train: \", time_train, \"sec\")\n",
        "print(\"Average time per epoch: \", av_time_epoch, \"sec\")\n",
        "print(\"Average time per image: \", av_time_img, \"sec\")"
      ],
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "mTl4F-BBIsWc",
        "outputId": "3f81fe58-c492-478b-9b95-d87427d22ed4"
      },
      "execution_count": null,
      "outputs": [
        {
          "output_type": "stream",
          "name": "stderr",
          "text": [
            "/usr/local/lib/python3.9/dist-packages/keras/initializers/initializers.py:120: UserWarning: The initializer HeNormal is unseeded and being called multiple times, which will return identical values each time (even if the initializer is unseeded). Please update your code to provide a seed to the initializer, or avoid using the same initalizer instance more than once.\n",
            "  warnings.warn(\n"
          ]
        },
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Model: \"U-Net\"\n",
            "__________________________________________________________________________________________________\n",
            " Layer (type)                   Output Shape         Param #     Connected to                     \n",
            "==================================================================================================\n",
            " input_1 (InputLayer)           [(None, 100, 100, 3  0           []                               \n",
            "                                )]                                                                \n",
            "                                                                                                  \n",
            " conv2d (Conv2D)                (None, 98, 98, 64)   1792        ['input_1[0][0]']                \n",
            "                                                                                                  \n",
            " activation (Activation)        (None, 98, 98, 64)   0           ['conv2d[0][0]']                 \n",
            "                                                                                                  \n",
            " conv2d_1 (Conv2D)              (None, 96, 96, 64)   36928       ['activation[0][0]']             \n",
            "                                                                                                  \n",
            " activation_1 (Activation)      (None, 96, 96, 64)   0           ['conv2d_1[0][0]']               \n",
            "                                                                                                  \n",
            " max_pooling2d (MaxPooling2D)   (None, 48, 48, 64)   0           ['activation_1[0][0]']           \n",
            "                                                                                                  \n",
            " conv2d_2 (Conv2D)              (None, 46, 46, 128)  73856       ['max_pooling2d[0][0]']          \n",
            "                                                                                                  \n",
            " activation_2 (Activation)      (None, 46, 46, 128)  0           ['conv2d_2[0][0]']               \n",
            "                                                                                                  \n",
            " conv2d_3 (Conv2D)              (None, 44, 44, 128)  147584      ['activation_2[0][0]']           \n",
            "                                                                                                  \n",
            " activation_3 (Activation)      (None, 44, 44, 128)  0           ['conv2d_3[0][0]']               \n",
            "                                                                                                  \n",
            " max_pooling2d_1 (MaxPooling2D)  (None, 22, 22, 128)  0          ['activation_3[0][0]']           \n",
            "                                                                                                  \n",
            " conv2d_4 (Conv2D)              (None, 20, 20, 256)  295168      ['max_pooling2d_1[0][0]']        \n",
            "                                                                                                  \n",
            " activation_4 (Activation)      (None, 20, 20, 256)  0           ['conv2d_4[0][0]']               \n",
            "                                                                                                  \n",
            " conv2d_5 (Conv2D)              (None, 18, 18, 256)  590080      ['activation_4[0][0]']           \n",
            "                                                                                                  \n",
            " activation_5 (Activation)      (None, 18, 18, 256)  0           ['conv2d_5[0][0]']               \n",
            "                                                                                                  \n",
            " center_crop (CenterCrop)       (None, 36, 36, 128)  0           ['activation_3[0][0]']           \n",
            "                                                                                                  \n",
            " conv2d_transpose (Conv2DTransp  (None, 36, 36, 128)  131200     ['activation_5[0][0]']           \n",
            " ose)                                                                                             \n",
            "                                                                                                  \n",
            " concatenate (Concatenate)      (None, 36, 36, 256)  0           ['center_crop[0][0]',            \n",
            "                                                                  'conv2d_transpose[0][0]']       \n",
            "                                                                                                  \n",
            " conv2d_6 (Conv2D)              (None, 34, 34, 128)  295040      ['concatenate[0][0]']            \n",
            "                                                                                                  \n",
            " activation_6 (Activation)      (None, 34, 34, 128)  0           ['conv2d_6[0][0]']               \n",
            "                                                                                                  \n",
            " conv2d_7 (Conv2D)              (None, 32, 32, 128)  147584      ['activation_6[0][0]']           \n",
            "                                                                                                  \n",
            " activation_7 (Activation)      (None, 32, 32, 128)  0           ['conv2d_7[0][0]']               \n",
            "                                                                                                  \n",
            " center_crop_1 (CenterCrop)     (None, 64, 64, 64)   0           ['activation_1[0][0]']           \n",
            "                                                                                                  \n",
            " conv2d_transpose_1 (Conv2DTran  (None, 64, 64, 64)  32832       ['activation_7[0][0]']           \n",
            " spose)                                                                                           \n",
            "                                                                                                  \n",
            " concatenate_1 (Concatenate)    (None, 64, 64, 128)  0           ['center_crop_1[0][0]',          \n",
            "                                                                  'conv2d_transpose_1[0][0]']     \n",
            "                                                                                                  \n",
            " conv2d_8 (Conv2D)              (None, 62, 62, 64)   73792       ['concatenate_1[0][0]']          \n",
            "                                                                                                  \n",
            " activation_8 (Activation)      (None, 62, 62, 64)   0           ['conv2d_8[0][0]']               \n",
            "                                                                                                  \n",
            " conv2d_9 (Conv2D)              (None, 60, 60, 64)   36928       ['activation_8[0][0]']           \n",
            "                                                                                                  \n",
            " activation_9 (Activation)      (None, 60, 60, 64)   0           ['conv2d_9[0][0]']               \n",
            "                                                                                                  \n",
            " conv2d_10 (Conv2D)             (None, 60, 60, 3)    195         ['activation_9[0][0]']           \n",
            "                                                                                                  \n",
            "==================================================================================================\n",
            "Total params: 1,862,979\n",
            "Trainable params: 1,862,979\n",
            "Non-trainable params: 0\n",
            "__________________________________________________________________________________________________\n",
            "Epoch 1/2\n",
            "275/275 [==============================] - ETA: 0s - loss: 0.2768 - accuracy: 0.5801"
          ]
        },
        {
          "output_type": "stream",
          "name": "stderr",
          "text": [
            "WARNING:tensorflow:`evaluate()` received a value for `sample_weight`, but `weighted_metrics` were not provided.  Did you mean to pass metrics to `weighted_metrics` in `compile()`?  If this is intentional you can pass `weighted_metrics=[]` to `compile()` in order to silence this warning.\n"
          ]
        },
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\r275/275 [==============================] - 387s 1s/step - loss: 0.2768 - accuracy: 0.5801 - val_loss: 0.2916 - val_accuracy: 0.5452\n",
            "Epoch 2/2\n",
            "275/275 [==============================] - ETA: 0s - loss: 0.2710 - accuracy: 0.5804"
          ]
        },
        {
          "output_type": "stream",
          "name": "stderr",
          "text": [
            "WARNING:tensorflow:`evaluate()` received a value for `sample_weight`, but `weighted_metrics` were not provided.  Did you mean to pass metrics to `weighted_metrics` in `compile()`?  If this is intentional you can pass `weighted_metrics=[]` to `compile()` in order to silence this warning.\n"
          ]
        },
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\r275/275 [==============================] - 383s 1s/step - loss: 0.2710 - accuracy: 0.5804 - val_loss: 0.2772 - val_accuracy: 0.5561\n",
            "The time of train:  807 sec\n",
            "Average time per epoch:  403.5 sec\n",
            "Average time per image:  1.4672727272727273 sec\n"
          ]
        }
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "model.save_weights(\"model_weights.h5\")"
      ],
      "metadata": {
        "id": "nQoi_BVkUj3F"
      },
      "execution_count": null,
      "outputs": []
    },
    {
      "cell_type": "code",
      "source": [
        "# Test the model\n",
        "score = model.evaluate(test_batches, verbose=0)\n",
        "print(f'Test loss: {score[0]} / Test accuracy: {score[1]}')"
      ],
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "1xW5leTvmWtV",
        "outputId": "757a7b28-b657-489f-bf03-a5131929c198"
      },
      "execution_count": null,
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Test loss: 0.9140134453773499 / Test accuracy: 0.5744739770889282\n"
          ]
        }
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "sum = 0\n",
        "sum_time = 0\n",
        "# Take first batch from the test images\n",
        "for images, masks in test_batches.take(10):\n",
        "\n",
        "    # Generate prediction for each image\n",
        "    start_inf = time.time()\n",
        "    predicted_masks = model.predict(images)\n",
        "    end_inf = time.time()\n",
        "    sum += 1\n",
        "    sum_time += (end_inf-start_inf)\n",
        "\n",
        "av_time_inf = (sum_time / sum)\n",
        "print(\"Average time of inference \", sum, \" img: \", av_time_inf, \"s/step       sum time: \", sum_time)"
      ],
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "JdA0-EOcpts6",
        "outputId": "64a0a223-f5cc-439d-fd83-002541ad7ac0"
      },
      "execution_count": null,
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "1/1 [==============================] - 1s 798ms/step\n",
            "1/1 [==============================] - 0s 316ms/step\n",
            "1/1 [==============================] - 0s 306ms/step\n",
            "1/1 [==============================] - 0s 310ms/step\n",
            "1/1 [==============================] - 0s 308ms/step\n",
            "1/1 [==============================] - 0s 311ms/step\n",
            "1/1 [==============================] - 0s 316ms/step\n",
            "1/1 [==============================] - 0s 320ms/step\n",
            "1/1 [==============================] - 0s 318ms/step\n",
            "1/1 [==============================] - 0s 325ms/step\n",
            "Average time of inference  10  img:  0.4295851945877075 s/step       sum time:  4.295851945877075\n"
          ]
        }
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "with open('metrics.json', 'w') as f:\n",
        "    json.dump(history.history, f)\n",
        "\n",
        "data = {}\n",
        "data['time'] = []\n",
        "data['time'].append({\n",
        "    'Batch size': batch_size,\n",
        "    'Num epoch': num_epochs,\n",
        "    'Average time of inference': av_time_inf,\n",
        "    'The time of train': time_train,\n",
        "    'Average time per epoch': av_time_epoch,\n",
        "    'Average time per image': av_time_img\n",
        "})\n",
        "\n",
        "with open('time.json', 'w') as outfile:\n",
        "    json.dump(data, outfile)"
      ],
      "metadata": {
        "id": "SMh6GwXL0UFg"
      },
      "execution_count": null,
      "outputs": []
    }
  ]
}