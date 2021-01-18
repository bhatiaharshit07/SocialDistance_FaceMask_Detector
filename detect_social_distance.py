#!/usr/bin/env python



# imports
import cv2
import numpy as np
import time
import argparse

# own modules
import utills, plot

confid = 0.5
thresh = 0.5
mouse_pts = []


                                                       

def get_mouse_points(event, x, y, flags, param):

    global mouse_pts
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(mouse_pts) < 4:
            cv2.circle(image, (x, y), 5, (0, 0, 255), 10)
        else:
            cv2.circle(image, (x, y), 5, (255, 0, 0), 10)
            
        if len(mouse_pts) >= 1 and len(mouse_pts) <= 3:
            cv2.line(image, (x, y), (mouse_pts[len(mouse_pts)-1][0], mouse_pts[len(mouse_pts)-1][1]), (70, 70, 70), 2)
            if len(mouse_pts) == 3:
                cv2.line(image, (x, y), (mouse_pts[0][0], mouse_pts[0][1]), (70, 70, 70), 2)
        
        if "mouse_pts" not in globals():
            mouse_pts = []
        mouse_pts.append((x, y))
        #print("Point detected")
        #print(mouse_pts)
        


def calculate_social_distancing(vid_path, net, output_dir, output_vid, ln1):
    
    count = 0
    vs = cv2.VideoCapture(vid_path)    

    # Get video height, width and fps
    height = int(vs.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(vs.get(cv2.CAP_PROP_FRAME_WIDTH))
    fps = int(vs.get(cv2.CAP_PROP_FPS))
    
    # Set scale for birds eye view
    # Bird's eye view will only show ROI
    scale_w, scale_h = utills.get_scale(width, height)

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    output_movie = cv2.VideoWriter("./output_vid/distancing.avi", fourcc, fps, (width, height))
    bird_movie = cv2.VideoWriter("./output_vid/bird_eye_view.avi", fourcc, fps, (int(width * scale_w), int(height * scale_h)))
        
    points = []
    global image
    
    while True:

        (grabbed, frame) = vs.read()

        if not grabbed:
            print('here')
            break
            
        (H, W) = frame.shape[:2]
        
        # first frame will be used to draw ROI and horizontal and vertical 180 cm distance(unit length in both directions)
        if count == 0:
            while True:
                image = frame
                cv2.imshow("image", image)
                cv2.waitKey(1)
                if len(mouse_pts) == 8:
                    cv2.destroyWindow("image")
                    break
               
            points = mouse_pts      
                 
        
        src = np.float32(np.array(points[:4]))
        dst = np.float32([[0, H], [W, H], [W, 0], [0, 0]])
        prespective_transform = cv2.getPerspectiveTransform(src, dst)

        # using next 3 points for horizontal and vertical unit length(in this case 180 cm)
        pts = np.float32(np.array([points[4:7]]))
        warped_pt = cv2.perspectiveTransform(pts, prespective_transform)[0]
        
        # since bird eye view has property that all points are equidistant in horizontal and vertical direction.
        # distance_w and distance_h will give us 180 cm distance in both horizontal and vertical directions
        # (how many pixels will be there in 180cm length in horizontal and vertical direction of birds eye view),
        # which we can use to calculate distance between two humans in transformed view or bird eye view
        distance_w = np.sqrt((warped_pt[0][0] - warped_pt[1][0]) ** 2 + (warped_pt[0][1] - warped_pt[1][1]) ** 2)
        distance_h = np.sqrt((warped_pt[0][0] - warped_pt[2][0]) ** 2 + (warped_pt[0][1] - warped_pt[2][1]) ** 2)
        pnts = np.array(points[:4], np.int32)
        cv2.polylines(frame, [pnts], True, (70, 70, 70), thickness=2)
    
    ####################################################################################
    
        # YOLO v3
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (416, 416), swapRB=True, crop=False)
        net.setInput(blob)
        start = time.time()
        layerOutputs = net.forward(ln1)
        end = time.time()
        boxes = []
        confidences = []
        classIDs = []   
    
        for output in layerOutputs:
            for detection in output:
                scores = detection[5:]
                classID = np.argmax(scores)
                confidence = scores[classID]
                # detecting humans in frame
                if classID == 0:

                    if confidence > confid:

                        box = detection[0:4] * np.array([W, H, W, H])
                        (centerX, centerY, width, height) = box.astype("int")

                        x = int(centerX - (width / 2))
                        y = int(centerY - (height / 2))

                        boxes.append([x, y, int(width), int(height)])
                        confidences.append(float(confidence))
                        classIDs.append(classID)
                    
        idxs = cv2.dnn.NMSBoxes(boxes, confidences, confid, thresh)
        font = cv2.FONT_HERSHEY_PLAIN
        boxes1 = []
        for i in range(len(boxes)):
            if i in idxs:
                boxes1.append(boxes[i])
                x,y,w,h = boxes[i]
                
        if len(boxes1) == 0:
            count = count + 1
            continue
            
        # Here we will be using bottom center point of bounding box for all boxes and will transform all those
        # bottom center points to bird eye view
        person_points = utills.get_transformed_points(boxes1, prespective_transform)
        
        # Here we will calculate distance between transformed points(humans)
        distances_mat, bxs_mat = utills.get_distances(boxes1, person_points, distance_w, distance_h)
        risk_count = utills.get_count(distances_mat)
    
        frame1 = np.copy(frame)
        
        # Draw bird eye view and frame with bouding boxes around humans according to risk factor    
        bird_image = plot.bird_eye_view(frame, distances_mat, person_points, scale_w, scale_h, risk_count)
        img = plot.social_distancing_view(frame1, bxs_mat, boxes1, risk_count)
        
        # Show/write image and videos
        if count != 0:
            output_movie.write(img)
            bird_movie.write(bird_image)
    
            cv2.imshow('Bird Eye View', bird_image)
            cv2.imshow('Camera view', img)
            #cv2.imwrite(output_dir+"frame%d.jpg" % count, img)
            #cv2.imwrite(output_dir+"bird_eye_view/frame%d.jpg" % count, bird_image)
    
        count = count + 1
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
     
    vs.release()
    cv2.destroyAllWindows() 
        

if __name__== "__main__":

    # Receives arguements specified by user
    parser = argparse.ArgumentParser()
    
    parser.add_argument('-v', '--video_path', action='store', dest='video_path', default='./data/example.mp4' ,
                    help='Path for input video')
                    
    parser.add_argument('-o', '--output_dir', action='store', dest='output_dir', default='./output/' ,
                    help='Path for Output images')
    
    parser.add_argument('-O', '--output_vid', action='store', dest='output_vid', default='./output_vid/' ,
                    help='Path for Output videos')

    parser.add_argument('-m', '--model', action='store', dest='model', default='./models/',
                    help='Path for models directory')
                    
    parser.add_argument('-u', '--uop', action='store', dest='uop', default='NO',
                    help='Use open pose or not (YES/NO)')
                    
    values = parser.parse_args()
    
    model_path = values.model
    if model_path[len(model_path) - 1] != '/':
        model_path = model_path + '/'
        
    output_dir = values.output_dir
    if output_dir[len(output_dir) - 1] != '/':
        output_dir = output_dir + '/'
    
    output_vid = values.output_vid
    if output_vid[len(output_vid) - 1] != '/':
        output_vid = output_vid + '/'


    # load Yolov3 weights
    
    weightsPath = model_path + "yolov3.weights"
    configPath = model_path + "yolov3.cfg"

    # load Yolov3-tiny weights

    #weightsPath = model_path + "yolov3-tiny.weights"
    #configPath = model_path + "yolov3-tiny.cfg"

    net_yl = cv2.dnn.readNetFromDarknet(configPath, weightsPath)
    ln = net_yl.getLayerNames()
    ln1 = [ln[i[0] - 1] for i in net_yl.getUnconnectedOutLayers()]

    # set mouse callback 

    cv2.namedWindow("image")
    cv2.setMouseCallback("image", get_mouse_points)
    np.random.seed(42)
    
    calculate_social_distancing(values.video_path, net_yl, output_dir, output_vid, ln1)



