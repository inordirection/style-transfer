import tensorflow as tf
import numpy as np 
import scipy.io  
import argparse 
import struct
import errno
import time                       
import cv2
import os

# Modified from https://github.com/cysmith/neural-style-tf

'''
  parsing and configuration
'''
def parse_args():

  desc = "TensorFlow implementation of 'A Neural Algorithm for Artistic Style'"  
  parser = argparse.ArgumentParser(description=desc)

  # options for single image
  parser.add_argument('--verbose', action='store_true',
    help='Boolean flag indicating if statements should be printed to the console.')

  parser.add_argument('--img_name', type=str, 
    help='Filename of the output image (auto-generated by default).')

  parser.add_argument('--style_imgs', nargs='+', type=str,
    help='Filenames of the style images (example: starry-night.jpg)', 
    required=True)
  
  parser.add_argument('--style_imgs_weights', nargs='+', type=float,
    default=[1.0],
    help='Interpolation weights of each of the style images. (example: 0.5 0.5)')
  
  parser.add_argument('--content_img', type=str,
    help='Filename of the content image (example: lion.jpg)')

  parser.add_argument('--style_imgs_dir', type=str,
    default='./styles',
    help='Directory path to the style images. (default: %(default)s)')

  parser.add_argument('--content_img_dir', type=str,
    default='./image_input',
    help='Directory path to the content image. (default: %(default)s)')
  
  parser.add_argument('--max_size', type=int, 
    default=512,
    help='Maximum width or height of the input images. (default: %(default)s)')
  
  parser.add_argument('--content_weight', type=float, 
    default=5e0,
    help='Weight for the content loss function. (default: %(default)s)')
  
  parser.add_argument('--style_weight', type=float, 
    default=1e4,
    help='Weight for the style loss function. (default: %(default)s)')
  
  parser.add_argument('--tv_weight', type=float, 
    default=1e-3,
    help='Weight for the total variational loss function. Set small (e.g. 1e-3). (default: %(default)s)')

  parser.add_argument('--content_layers', nargs='+', type=str, 
    default=['conv4_2'],
    help='VGG19 layers used for the content image. (default: %(default)s)')
  
  parser.add_argument('--style_layers', nargs='+', type=str,
    default=['relu1_1', 'relu2_1', 'relu3_1', 'relu4_1', 'relu5_1'],
    help='VGG19 layers used for the style image. (default: %(default)s)')
  
  parser.add_argument('--content_layer_weights', nargs='+', type=float, 
    default=[1.0], 
    help='Contributions (weights) of each content layer to loss. (default: %(default)s)')
  
  parser.add_argument('--style_layer_weights', nargs='+', type=float, 
    default=[0.2, 0.2, 0.2, 0.2, 0.2],
    help='Contributions (weights) of each style layer to loss. (default: %(default)s)')
    
  parser.add_argument('--seed', type=int, 
    default=0,
    help='Seed for the random number generator. (default: %(default)s)')
  
  parser.add_argument('--model_weights', type=str, 
    default='imagenet-vgg-verydeep-19.mat',
    help='Weights and biases of the VGG-19 network.')
  
  parser.add_argument('--device', type=str, 
    default='/gpu:0',
    choices=['/gpu:0', '/cpu:0'],
    help='GPU or CPU mode.  GPU mode requires NVIDIA CUDA. (default|recommended: %(default)s)')
  
  parser.add_argument('--img_output_dir', type=str, 
    default='./image_output',
    help='Relative or absolute directory path to output image and data.')
  
  # optimizations
  parser.add_argument('--optimizer', type=str, 
    default='lbfgs',
    choices=['lbfgs', 'adam'],
    help='Loss minimization optimizer.  L-BFGS gives better results.  Adam uses less memory. (default|recommended: %(default)s)')
  
  parser.add_argument('--learning_rate', type=float, 
    default=1e1, 
    help='Learning rate parameter for the Adam optimizer. (default: %(default)s)')
  
  parser.add_argument('--beta1', type=float, 
    default=0.9, 
    help='First momentum parameter for the Adam optimizer. (default: %(default)s)')

  parser.add_argument('--beta1', type=float, 
    default=0.999, 
    help='Second momentum parameter for the Adam optimizer. (default: %(default)s)')
  
  parser.add_argument('--epsilon', type=float, 
    default=1e-8, 
    help='Numerical stability constant for the Adam optimizer. (default: %(default)s)')
  
  parser.add_argument('--blocks', type=int, 
    default=1,
    # note: interupting BFGS training into blocks to save output makes it go slower
    help='Number of times to save intermediary L-BFGS image output. (default: %(default)s)')
 
  parser.add_argument('--max_iterations', type=int, 
    default=1000,
    help='Max number of iterations per block for the optimizer. (default: %(default)s)')

  parser.add_argument('--print_iterations', type=int, 
    default=50,
    help='Number of iterations between optimizer print statements (and Adam image output). (default: %(default)s)')

  args = parser.parse_args()

  # normalize weights
  args.style_layer_weights   = normalize(args.style_layer_weights)
  args.content_layer_weights = normalize(args.content_layer_weights)
  args.style_imgs_weights    = normalize(args.style_imgs_weights)

  # create directories for output
  maybe_make_directory(args.img_output_dir)

  return args

'''
  pre-trained vgg19 convolutional neural network
  remark: layers are manually initialized for clarity.
'''

def build_model(input_img):
  if args.verbose: print('\nBUILDING VGG-19 NETWORK')
  net = {}
  _, h, w, d     = input_img.shape
  
  if args.verbose: print('loading model weights...')
  vgg_rawnet     = scipy.io.loadmat(args.model_weights)
  vgg_layers     = vgg_rawnet['layers'][0]
  if args.verbose: print('constructing layers...')
  net['input']   = tf.Variable(np.zeros((1, h, w, d), dtype=np.float32))

  if args.verbose: print('LAYER GROUP 1')
  net['conv1_1'] = conv_layer('conv1_1', net['input'], W=get_weights(vgg_layers, 0))
  net['relu1_1'] = relu_layer('relu1_1', net['conv1_1'], b=get_bias(vgg_layers, 0))

  net['conv1_2'] = conv_layer('conv1_2', net['relu1_1'], W=get_weights(vgg_layers, 2))
  net['relu1_2'] = relu_layer('relu1_2', net['conv1_2'], b=get_bias(vgg_layers, 2))
  
  net['pool1']   = pool_layer('pool1', net['relu1_2'])

  if args.verbose: print('LAYER GROUP 2')  
  net['conv2_1'] = conv_layer('conv2_1', net['pool1'], W=get_weights(vgg_layers, 5))
  net['relu2_1'] = relu_layer('relu2_1', net['conv2_1'], b=get_bias(vgg_layers, 5))
  
  net['conv2_2'] = conv_layer('conv2_2', net['relu2_1'], W=get_weights(vgg_layers, 7))
  net['relu2_2'] = relu_layer('relu2_2', net['conv2_2'], b=get_bias(vgg_layers, 7))
  
  net['pool2']   = pool_layer('pool2', net['relu2_2'])
  
  if args.verbose: print('LAYER GROUP 3')
  net['conv3_1'] = conv_layer('conv3_1', net['pool2'], W=get_weights(vgg_layers, 10))
  net['relu3_1'] = relu_layer('relu3_1', net['conv3_1'], b=get_bias(vgg_layers, 10))

  net['conv3_2'] = conv_layer('conv3_2', net['relu3_1'], W=get_weights(vgg_layers, 12))
  net['relu3_2'] = relu_layer('relu3_2', net['conv3_2'], b=get_bias(vgg_layers, 12))

  net['conv3_3'] = conv_layer('conv3_3', net['relu3_2'], W=get_weights(vgg_layers, 14))
  net['relu3_3'] = relu_layer('relu3_3', net['conv3_3'], b=get_bias(vgg_layers, 14))

  net['conv3_4'] = conv_layer('conv3_4', net['relu3_3'], W=get_weights(vgg_layers, 16))
  net['relu3_4'] = relu_layer('relu3_4', net['conv3_4'], b=get_bias(vgg_layers, 16))

  net['pool3']   = pool_layer('pool3', net['relu3_4'])

  if args.verbose: print('LAYER GROUP 4')
  net['conv4_1'] = conv_layer('conv4_1', net['pool3'], W=get_weights(vgg_layers, 19))
  net['relu4_1'] = relu_layer('relu4_1', net['conv4_1'], b=get_bias(vgg_layers, 19))

  net['conv4_2'] = conv_layer('conv4_2', net['relu4_1'], W=get_weights(vgg_layers, 21))
  net['relu4_2'] = relu_layer('relu4_2', net['conv4_2'], b=get_bias(vgg_layers, 21))

  net['conv4_3'] = conv_layer('conv4_3', net['relu4_2'], W=get_weights(vgg_layers, 23))
  net['relu4_3'] = relu_layer('relu4_3', net['conv4_3'], b=get_bias(vgg_layers, 23))

  net['conv4_4'] = conv_layer('conv4_4', net['relu4_3'], W=get_weights(vgg_layers, 25))
  net['relu4_4'] = relu_layer('relu4_4', net['conv4_4'], b=get_bias(vgg_layers, 25))

  net['pool4']   = pool_layer('pool4', net['relu4_4'])

  if args.verbose: print('LAYER GROUP 5')
  net['conv5_1'] = conv_layer('conv5_1', net['pool4'], W=get_weights(vgg_layers, 28))
  net['relu5_1'] = relu_layer('relu5_1', net['conv5_1'], b=get_bias(vgg_layers, 28))

  net['conv5_2'] = conv_layer('conv5_2', net['relu5_1'], W=get_weights(vgg_layers, 30))
  net['relu5_2'] = relu_layer('relu5_2', net['conv5_2'], b=get_bias(vgg_layers, 30))

  net['conv5_3'] = conv_layer('conv5_3', net['relu5_2'], W=get_weights(vgg_layers, 32))
  net['relu5_3'] = relu_layer('relu5_3', net['conv5_3'], b=get_bias(vgg_layers, 32))

  net['conv5_4'] = conv_layer('conv5_4', net['relu5_3'], W=get_weights(vgg_layers, 34))
  net['relu5_4'] = relu_layer('relu5_4', net['conv5_4'], b=get_bias(vgg_layers, 34))

  net['pool5']   = pool_layer('pool5', net['relu5_4'])

  return net

def conv_layer(layer_name, layer_input, W):
  conv = tf.nn.conv2d(layer_input, W, strides=[1, 1, 1, 1], padding='SAME')
  if args.verbose: print('--{} | shape={} | weights_shape={}'.format(layer_name, 
    conv.get_shape(), W.get_shape()))
  return conv

def relu_layer(layer_name, layer_input, b):
  relu = tf.nn.relu(layer_input + b)
  if args.verbose: 
    print('--{} | shape={} | bias_shape={}'.format(layer_name, relu.get_shape(), 
      b.get_shape()))
  return relu

def pool_layer(layer_name, layer_input):
  pool = tf.nn.avg_pool(layer_input, ksize=[1, 2, 2, 1], # could also do a max pool
    strides=[1, 2, 2, 1], padding='SAME')
  if args.verbose: 
    print('--{}   | shape={}'.format(layer_name, pool.get_shape()))
  return pool

def get_weights(vgg_layers, i):
  weights = vgg_layers[i][0][0][2][0][0]
  W = tf.constant(weights)
  return W

def get_bias(vgg_layers, i):
  bias = vgg_layers[i][0][0][2][0][1]
  b = tf.constant(np.reshape(bias, (bias.size)))
  return b

'''
  'a neural algorithm for artistic style' loss functions
'''
def content_layer_loss(p, x):
  _, h, w, d = p.get_shape()
  M = h.value * w.value
  N = d.value
  K = 1. / (2. * N**0.5 * M**0.5)
  loss = K * tf.reduce_sum(tf.pow((x - p), 2))
  return loss

def style_layer_loss(a, x):
  _, h, w, d = a.get_shape()
  M = h.value * w.value
  N = d.value
  A = gram_matrix(a, M, N)
  G = gram_matrix(x, M, N)
  loss = (1./(4 * N**2 * M**2)) * tf.reduce_sum(tf.pow((G - A), 2))
  return loss

def gram_matrix(x, area, depth):
  F = tf.reshape(x, (area, depth))
  G = tf.matmul(tf.transpose(F), F)
  return G

def sum_style_losses(sess, net, style_imgs):
  total_style_loss = 0.
  weights = args.style_imgs_weights
  for img, img_weight in zip(style_imgs, weights):
    sess.run(net['input'].assign(img))
    style_loss = 0.
    for layer, weight in zip(args.style_layers, args.style_layer_weights):
      a = sess.run(net[layer])
      x = net[layer]
      a = tf.convert_to_tensor(a)
      style_loss += style_layer_loss(a, x) * weight
    style_loss /= float(len(args.style_layers))
    total_style_loss += (style_loss * img_weight)
  total_style_loss /= float(len(style_imgs))
  return total_style_loss

def sum_content_losses(sess, net, content_img):
  sess.run(net['input'].assign(content_img))
  content_loss = 0.
  for layer, weight in zip(args.content_layers, args.content_layer_weights):
    p = sess.run(net[layer])
    x = net[layer]
    p = tf.convert_to_tensor(p)
    content_loss += content_layer_loss(p, x) * weight
  content_loss /= float(len(args.content_layers))
  return content_loss

'''
  utilities and i/o
'''
def read_image(path):
  # bgr image
  img = cv2.imread(path, cv2.IMREAD_COLOR)
  check_image(img, path)
  img = img.astype(np.float32)
  img = preprocess(img)
  return img

def write_image(path, img):
  img = postprocess(img)
  cv2.imwrite(path, img)

def preprocess(img):
  imgpre = np.copy(img)
  # bgr to rgb
  imgpre = imgpre[...,::-1]
  # shape (h, w, d) to (1, h, w, d)
  imgpre = imgpre[np.newaxis,:,:,:]
  imgpre -= np.array([123.68, 116.779, 103.939]).reshape((1,1,1,3))
  return imgpre

def postprocess(img):
  imgpost = np.copy(img)
  imgpost += np.array([123.68, 116.779, 103.939]).reshape((1,1,1,3))
  # shape (1, h, w, d) to (h, w, d)
  imgpost = imgpost[0]
  imgpost = np.clip(imgpost, 0, 255).astype('uint8')
  # rgb to bgr
  imgpost = imgpost[...,::-1]
  return imgpost

def read_weights_file(path):
  lines = open(path).readlines()
  header = list(map(int, lines[0].split(' ')))
  w = header[0]
  h = header[1]
  vals = np.zeros((h, w), dtype=np.float32)
  for i in range(1, len(lines)):
    line = lines[i].rstrip().split(' ')
    vals[i-1] = np.array(list(map(np.float32, line)))
    vals[i-1] = list(map(lambda x: 0. if x < 255. else 1., vals[i-1]))
  # expand to 3 channels
  weights = np.dstack([vals.astype(np.float32)] * 3)
  return weights

def normalize(weights):
  denom = sum(weights)
  if denom > 0.:
    return [float(i) / denom for i in weights]
  else: return [0.] * len(weights)

def maybe_make_directory(dir_path):
  if not os.path.exists(dir_path):  
    os.makedirs(dir_path)

def check_image(img, path):
  if img is None:
    raise OSError(errno.ENOENT, "No such file", path)

'''
  rendering -- where the magic happens
'''
def stylize(content_img, style_imgs, init_img, frame=None):
  with tf.device(args.device), tf.Session() as sess:
    # setup network
    net = build_model(content_img)
    
    # style loss
    L_style = sum_style_losses(sess, net, style_imgs)
    
    # content loss
    L_content = sum_content_losses(sess, net, content_img)
    
    # denoising loss
    L_tv = tf.image.total_variation(net['input'])
    
    # loss weights
    alpha = args.content_weight
    beta  = args.style_weight
    theta = args.tv_weight
    
    # total loss
    L_total  = alpha * L_content
    L_total += beta  * L_style
    L_total += theta * L_tv
       
    # optimization algorithm
    optimizer = get_optimizer(L_total)

    if args.optimizer == 'adam':
      minimize_with_adam(sess, net, optimizer, init_img, L_total)
    elif args.optimizer == 'lbfgs':
      minimize_with_lbfgs(sess, net, optimizer, init_img)
    
    output_img = sess.run(net['input'])
    
    write_image_output(output_img, content_img, style_imgs)

def minimize_with_lbfgs(sess, net, optimizer, init_img):
  if args.verbose: print('\nMINIMIZING LOSS USING: L-BFGS OPTIMIZER')
  init_op = tf.global_variables_initializer()
  sess.run(init_op)
  sess.run(net['input'].assign(init_img))
  block = 0
  while block < args.blocks:
    if args.verbose: print('\nBLOCK {}'.format(block))
    optimizer.minimize(sess)
    output_img = sess.run(net['input'])
    out_dir, img_path = get_image_savename(block, args.max_iterations)
    write_image(img_path, output_img)
    block += 1

def minimize_with_adam(sess, net, optimizer, init_img, loss):
  if args.verbose: print('\nMINIMIZING LOSS USING: ADAM OPTIMIZER')
  train_op = optimizer.minimize(loss)
  init_op = tf.global_variables_initializer()
  sess.run(init_op)
  sess.run(net['input'].assign(init_img))
  block = 0
  while block < args.blocks:
    if args.verbose: print('\nBLOCK {}'.format(block))
    iteration = 0
    while (iteration < args.max_iterations):
      sess.run(train_op)
      # print output and save intermediary images
      if iteration % args.print_iterations == 0 and args.verbose:
        curr_loss = loss.eval()
        print("At iterate {}\tf=  {}".format(iteration, curr_loss))
        output_img = sess.run(net['input'])
        out_dir, img_path = get_image_savename(block, iteration)
        write_image(img_path, output_img)
      iteration += 1
    block += 1

def get_optimizer(loss):
  print_iterations = args.print_iterations if args.verbose else 0
  if args.optimizer == 'lbfgs':
    optimizer = tf.contrib.opt.ScipyOptimizerInterface(
      loss, method='L-BFGS-B',
      options={'maxiter': args.max_iterations,
                  'disp': print_iterations})
  elif args.optimizer == 'adam':
    optimizer = tf.train.AdamOptimizer(args.learning_rate, args.beta1, args.beta2, args.epsilon)
  return optimizer

def get_image_savename(block, iteration):
  if args.img_name != None:
    out_dir = os.path.join(args.img_output_dir, args.img_name)
  else:
    out_subdir = args.content_img[:-4]+'.'+args.style_imgs[0][:-4]
    out_dir = os.path.join(args.img_output_dir, out_subdir)

  out_dir += str(args.max_size)
  if args.optimizer == 'adam':
    out_dir += 'A'
    out_dir += '('str(args.learning_rate)+','str(args.beta1)+','+str(args.beta2)
                +','+str(args.epsilon)+')'
  else:
    out_dir += 'LBFGS'
  if args.blocks != 1:
    out_dir += str(args.blocks) + 'x'
  out_dir += str(args.max_iterations)
  # store intermediary images in 'iters' subfolder
  if block < args.blocks or iteration < args.max_iterations:
    out_dir = os.path.join(out_dir, 'iters')
  maybe_make_directory(out_dir)

  if args.img_name != None:
    img_path = os.path.join(out_dir, args.img_name)
  else:
    img_path = os.path.join(out_dir, str(block)+'.'+str(iteration)+'.png')

  return out_dir, img_path

def write_image_output(output_img, content_img, style_imgs):
  out_dir, img_path = get_image_savename(args.blocks, 0)
  content_path = os.path.join(out_dir, '0content.png')

  write_image(img_path, output_img)
  write_image(content_path, content_img)
  index = 0
  for style_img in style_imgs:
    path = os.path.join(out_dir, str(index)+'_style.png')
    write_image(path, style_img)
    index += 1
  
  # save the configuration settings
  out_file = os.path.join(out_dir, 'meta_data.txt')
  f = open(out_file, 'w')
  f.write('image_name: {}\n'.format(args.img_name))
  f.write('content: {}\n'.format(args.content_img))
  index = 0
  for style_img, weight in zip(args.style_imgs, args.style_imgs_weights):
    f.write('styles['+str(index)+']: {} * {}\n'.format(weight, style_img))
    index += 1
  f.write('content_weight: {}\n'.format(args.content_weight))
  f.write('style_weight: {}\n'.format(args.style_weight))
  f.write('tv_weight: {}\n'.format(args.tv_weight))
  f.write('content_layers: {}\n'.format(args.content_layers))
  f.write('style_layers: {}\n'.format(args.style_layers))
  f.write('optimizer_type: {}\n'.format(args.optimizer))
  f.write('training_blocks: {}\n'.format(args.blocks))
  f.write('max_iterations: {}\n'.format(args.max_iterations))
  f.write('max_image_size: {}\n'.format(args.max_size))
  f.close()

'''
  image loading and processing
'''
def get_content_image(content_img):
  path = os.path.join(args.content_img_dir, content_img)
   # bgr image
  img = cv2.imread(path, cv2.IMREAD_COLOR)
  check_image(img, path)
  img = img.astype(np.float32)
  h, w, d = img.shape
  mx = args.max_size
  # resize if > max size
  if h > w and h > mx:
    w = (float(mx) / float(h)) * w
    img = cv2.resize(img, dsize=(int(w), mx), interpolation=cv2.INTER_AREA)
  if w > mx:
    h = (float(mx) / float(w)) * h
    img = cv2.resize(img, dsize=(mx, int(h)), interpolation=cv2.INTER_AREA)
  img = preprocess(img)
  return img

def get_style_images(content_img):
  _, ch, cw, cd = content_img.shape
  style_imgs = []
  for style_fn in args.style_imgs:
    path = os.path.join(args.style_imgs_dir, style_fn)
    # bgr image
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    check_image(img, path)
    img = img.astype(np.float32)
    img = cv2.resize(img, dsize=(cw, ch), interpolation=cv2.INTER_AREA)
    img = preprocess(img)
    style_imgs.append(img)
  return style_imgs

def render_image():
  content_img = get_content_image(args.content_img)
  style_imgs = get_style_images(content_img)
  with tf.Graph().as_default():
    print('\n---- RENDERING IMAGE ----\n')
    init_img = content_img # could replace with style img or noise
    tick = time.time()
    stylize(content_img, style_imgs, init_img)
    tock = time.time()
    print('Elapsed time: {}'.format(tock - tick))

def main():
  tf.logging.set_verbosity(tf.logging.ERROR) # quiet TF errors
  global args
  args = parse_args()
  render_image()

if __name__ == '__main__':
  main()
