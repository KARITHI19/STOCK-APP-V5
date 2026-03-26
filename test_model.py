import tensorflow as tf

model = tf.keras.models.load_model("multivariate_lstm.keras")
print("Model loaded successfully")
print("Input shape:", model.input_shape)
print("Output shape:", model.output_shape)