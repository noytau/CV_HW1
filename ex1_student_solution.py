"""Projective Homography and Panorama Solution."""
import numpy as np

from typing import Tuple
from random import sample
from collections import namedtuple


from numpy.linalg import svd
from scipy.interpolate import griddata


PadStruct = namedtuple('PadStruct',
                       ['pad_up', 'pad_down', 'pad_right', 'pad_left'])


class Solution:
    """Implement Projective Homography and Panorama Solution."""
    def __init__(self):
        pass

    @staticmethod
    def compute_homography_naive(match_p_src: np.ndarray,
                                 match_p_dst: np.ndarray) -> np.ndarray:
        """Compute a Homography in the Naive approach, using SVD decomposition.

        Args:
            match_p_src: 2xN points from the source image.
            match_p_dst: 2xN points from the destination image.

        Returns:
            Homography from source to destination, 3x3 numpy array.
        """
        # Create vectors of [x,y,1]
        N_size = match_p_dst.shape[1]  # Get the N dimension of matching points. meaning-number of matching points.
        ones_vector = np.ones((N_size, 1)).T
        match_p_src_vert = np.vstack((match_p_src, ones_vector))
        match_p_dst_vert = np.vstack((match_p_dst, ones_vector))
        zero_row_vector = np.zeros(3)

        # init a new matrix to obtain all matching point arranged with destination points.
        ref_mat = np.zeros((2 * N_size, 9))

        for i in range(0, N_size):

            # compute in each 2 rows the equation for x and for y
            x_row = np.hstack((match_p_src_vert[:, i].T, zero_row_vector,  -match_p_src_vert[:, i] * match_p_dst_vert[0][i].T))
            y_row = np.hstack((zero_row_vector, match_p_src_vert[:, i].T, -match_p_src_vert[:, i] * match_p_dst_vert[1][i].T))

            ref_mat[2 * i, :] = x_row
            ref_mat[2 * i + 1:, :] = y_row

        U, S, V = np.linalg.svd(ref_mat)
        # take the vector with the smallest singular values (descending order)
        H = np.reshape(V[-1], (3, 3))
        # return homography
        return H

    @staticmethod
    def compute_forward_homography_slow(
            homography: np.ndarray,
            src_image: np.ndarray,
            dst_image_shape: tuple = (1088, 1452, 3)) -> np.ndarray:
        """Compute a Forward-Homography in the Naive approach, using loops.

        Iterate over the rows and columns of the source image, and compute
        the corresponding point in the destination image using the
        projective homography. Place each pixel value from the source image
        to its corresponding location in the destination image.
        Don't forget to round the pixel locations computed using the
        homography.

        Args:
            homography: 3x3 Projective Homography matrix.
            src_image: HxWx3 source image.
            dst_image_shape: tuple of length 3 indicating the destination
            image height, width and color dimensions.

        Returns:
            The forward homography of the source image to its destination.
        """

        dst_image = np.zeros(dst_image_shape,  dtype=int)
        for row in range(src_image.shape[0]):
            for col in range(src_image.shape[1]):
                point = np.array([[col], [row], [1]], dtype=int)
                transformed_point = np.dot(homography, point)
                normalized_point = (int(transformed_point[0][0] / transformed_point[2][0]), int(transformed_point[1][0] / transformed_point[2][0]))
                # Check if point is in dest image
                if (normalized_point[0] in range(dst_image_shape[1])) and (normalized_point[1] in range(dst_image_shape[0])):
                    for channel in range(dst_image_shape[2]):
                        dst_image[normalized_point[1]][normalized_point[0]][channel] = src_image[row][col][channel]

        return dst_image

    @staticmethod
    def compute_forward_homography_fast(
            homography: np.ndarray,
            src_image: np.ndarray,
            dst_image_shape: tuple = (1088, 1452, 3)) -> np.ndarray:
        """Compute a Forward-Homography in a fast approach, WITHOUT loops.

        (1) Create a meshgrid of columns and rows.
        (2) Generate a matrix of size 3x(H*W) which stores the pixel locations
        in homogeneous coordinates.
        (3) Transform the source homogeneous coordinates to the target
        homogeneous coordinates with a simple matrix multiplication and
        apply the normalization you've seen in class.
        (4) Convert the coordinates into integer values and clip them
        according to the destination image size.
        (5) Plant the pixels from the source image to the target image according
        to the coordinates you found.

        Args:
            homography: 3x3 Projective Homography matrix.
            src_image: HxWx3 source image.
            dst_image_shape: tuple of length 3 indicating the destination.
            image height, width and color dimensions.

        Returns:
            The forward homography of the source image to its destination.
        """
        dst_image = np.zeros(dst_image_shape, dtype=int)
        # Setting meshgrid with indeices instead of meshgrid since meshgrid returns to arrays
        meshgrid_image = np.indices((src_image.shape[1], src_image.shape[0]))
        meshgrid_image = meshgrid_image.reshape(2, -1)
        meshgrid_image = np.vstack((meshgrid_image, np.ones(meshgrid_image.shape[1]))).astype(np.int)

        transformed_vectors = np.dot(homography, meshgrid_image)
        normalized_x = np.divide(np.array(transformed_vectors[0, :]), np.array(transformed_vectors[2, :])).astype(np.int)
        normalized_y = np.divide(np.array(transformed_vectors[1, :]), np.array(transformed_vectors[2, :])).astype(np.int)
        selected_points = np.where((normalized_x >= 0) & (normalized_x < dst_image_shape[1]) & (normalized_y >= 0) & (normalized_y < dst_image_shape[0]))
        x_cords = normalized_x[selected_points] # taking x,y coordinates
        y_cords = normalized_y[selected_points]

        # update meshgrid to contain only selected points
        meshgrid_image_x = meshgrid_image[0][selected_points]
        meshgrid_image_y = meshgrid_image[1][selected_points]

        dst_image[y_cords, x_cords] = src_image[meshgrid_image_y, meshgrid_image_x]
        return dst_image

    @staticmethod
    def get_vectors_and_inliers (homography: np.ndarray,
                        match_p_src: np.ndarray,
                        match_p_dst: np.ndarray,
                        max_err: float) -> (np.ndarray, np.ndarray, Tuple[float, float]):

        N_size = match_p_dst.shape[1]
        # concat ones to create vectors
        src_vector = np.vstack((match_p_src, np.ones(N_size))).astype(np.int)
        dst_vector = np.vstack((match_p_dst, np.ones(N_size))).astype(np.int)
        # compute homography
        src_vector_h = np.dot(homography, src_vector)
        src_vector_norm = (1 / src_vector_h[2]) * src_vector_h

        inliers = []
        for i in range(N_size):
            # compute error between calculated homography to given
            homography_err = np.linalg.norm(src_vector_norm[:, i] - dst_vector[:, i])
            if homography_err < max_err:
                inliers.append(i)

        return (src_vector_norm, dst_vector, inliers)

    @staticmethod
    def test_homography(homography: np.ndarray,
                        match_p_src: np.ndarray,
                        match_p_dst: np.ndarray,
                        max_err: float) -> Tuple[float, float]:
        """Calculate the quality of the projective transformation model.

        Args:
            homography: 3x3 Projective Homography matrix.
            match_p_src: 2xN points from the source image.
            match_p_dst: 2xN points from the destination image.
            max_err: A scalar that represents the maximum distance (in
            pixels) between the mapped src point to its corresponding dst
            point, in order to be considered as valid inlier.

        Returns:
            A tuple containing the following metrics to quantify the
            homography performance:
            fit_percent: The probability (between 0 and 1) validly mapped src
            points (inliers).
            dist_mse: Mean square error of the distances between validly
            mapped src points, to their corresponding dst points (only for
            inliers). In edge case where the number of inliers is zero,
            return dist_mse = 10 ** 9.
        """

        (src_vector_norm, dst_vector, inliers) = Solution.get_vectors_and_inliers(homography, match_p_src, match_p_dst,
                                                                                  max_err)
        if inliers:
            # distance between points is calculated with L2 norm
            dist_mse = np.linalg.norm(src_vector_norm[:, inliers] - dst_vector[:, inliers])
        else:
            dist_mse = 10 ** 9
        # calculate the percentage of inliers from given points
        fit_percent = len(inliers) / match_p_src.shape[1]

        return fit_percent, dist_mse

    @staticmethod
    def meet_the_model_points(homography: np.ndarray,
                              match_p_src: np.ndarray,
                              match_p_dst: np.ndarray,
                              max_err: float) -> Tuple[np.ndarray, np.ndarray]:
        """Return which matching points meet the homography.

        Loop through the matching points, and return the matching points from
        both images that are inliers for the given homography.

        Args:
            homography: 3x3 Projective Homography matrix.
            match_p_src: 2xN points from the source image.
            match_p_dst: 2xN points from the destination image.
            max_err: A scalar that represents the maximum distance (in
            pixels) between the mapped src point to its corresponding dst
            point, in order to be considered as valid inlier.
        Returns:
            A tuple containing two numpy nd-arrays, containing the matching
            points which meet the model (the homography). The first entry in
            the tuple is the matching points from the source image. That is a
            nd-array of size 2xD (D=the number of points which meet the model).
            The second entry is the matching points form the destination
            image (shape 2xD; D as above).
        """
        (_, _, inliers) = Solution.get_vectors_and_inliers(homography, match_p_src, match_p_dst,
                                                                                  max_err)
        mp_src_meets_model = match_p_src[:, inliers]
        mp_dst_meets_model = match_p_dst[:, inliers]

        return mp_src_meets_model, mp_dst_meets_model

    def compute_homography(self,
                           match_p_src: np.ndarray,
                           match_p_dst: np.ndarray,
                           inliers_percent: float,
                           max_err: float) -> np.ndarray:
        """Compute homography coefficients using RANSAC to overcome outliers.

        Args:
            match_p_src: 2xN points from the source image.
            match_p_dst: 2xN points from the destination image.
            inliers_percent: The expected probability (between 0 and 1) of
            correct match points from the entire list of match points.
            max_err: A scalar that represents the maximum distance (in
            pixels) between the mapped src point to its corresponding dst
            point, in order to be considered as valid inlier.
        Returns:
            homography: Projective transformation matrix from src to dst.
        """

        # use class notations:
        w = inliers_percent
        # t = max_err
        # p = parameter determining the probability of the algorithm to
        # succeed
        p = 0.99
        # the minimal probability of points which meets with the model
        d = 0.5
        # number of points sufficient to compute the model
        n = 4
        # number of RANSAC iterations (+1 to avoid the case where w=1)
        k = int(np.ceil(np.log(1 - p) / np.log(1 - w ** n))) + 1

        N_size = match_p_src.shape[1]
        # init mse value
        mse_value = 10 ** 9 + 1
        k = k * 10 # increase k to avoid unknown homographies
        # loop for k iterations
        for i in range(k):
            # randomly select n points
            random_selected_points = sample(range(N_size), n)  # random n indexes
            computed_homography = Solution.compute_homography_naive(match_p_src[:, random_selected_points],
                                                    match_p_dst[:, random_selected_points])
            mp_src_meets_model, mp_dst_meets_model = Solution.meet_the_model_points(computed_homography, match_p_src,
                                                                                    match_p_dst, max_err)
            fit_percent, dist_mse = Solution.test_homography(computed_homography, match_p_src, match_p_dst, max_err)

            if (fit_percent >= w):
                computed_homography = Solution.compute_homography_naive(mp_src_meets_model, mp_dst_meets_model)
                fit_percent, dist_mse = Solution.test_homography(computed_homography, match_p_src, match_p_dst, max_err)
                if (dist_mse < mse_value):
                    homography = computed_homography
                    mse_value = dist_mse
        return homography

    @staticmethod
    def compute_backward_mapping(
            backward_projective_homography: np.ndarray,
            src_image: np.ndarray,
            dst_image_shape: tuple = (1088, 1452, 3)) -> np.ndarray:
        """Compute backward mapping.

        (1) Create a mesh-grid of columns and rows of the destination image.
        (2) Create a set of homogenous coordinates for the destination image
        using the mesh-grid from (1).
        (3) Compute the corresponding coordinates in the source image using
        the backward projective homography.
        (4) Create the mesh-grid of source image coordinates.
        (5) For each color channel (RGB): Use scipy's interpolation.griddata
        with an appropriate configuration to compute the bi-cubic
        interpolation of the projected coordinates.

        Args:
            backward_projective_homography: 3x3 Projective Homography matrix.
            src_image: HxWx3 source image.
            dst_image_shape: tuple of length 3 indicating the destination shape.

        Returns:
            The source image backward warped to the destination coordinates.
        """

        # Create a mesh-grid of columns and rows of the destination image
        meshgrid_dst_matrix = np.indices((dst_image_shape[0], dst_image_shape[1])).reshape(2, -1)
        meshgrid_dst_matrix = np.vstack((meshgrid_dst_matrix, np.ones((meshgrid_dst_matrix.shape[1])))).astype(np.int)
        meshgrid_dst_matrix[[0,1]] = meshgrid_dst_matrix[[1,0]]
        # Create a set of homogenous coordinates for the destination image
        meshgrid_homography = np.dot(backward_projective_homography, meshgrid_dst_matrix)
        # Normalize vectors
        y_dst_cords = np.divide(np.array(meshgrid_homography[1, :]), np.array(meshgrid_homography[2,:])).astype(np.int)
        x_dst_cords = np.divide(np.array(meshgrid_homography[0, :]), np.array(meshgrid_homography[2,:])).astype(np.int)

        # Create the mesh-grid of source image coordinates
        meshgrid_src_matrix = np.indices((src_image.shape[0], src_image.shape[1])).reshape(2, -1)
        x_src_cords = meshgrid_src_matrix[1]
        y_src_cords = meshgrid_src_matrix[0]

        # Interpolate grid data values
        backward_warp = (griddata((x_src_cords, y_src_cords), src_image[y_src_cords, x_src_cords, :], (x_dst_cords, y_dst_cords), method='cubic')).reshape(dst_image_shape)
        return backward_warp

    @staticmethod
    def find_panorama_shape(src_image: np.ndarray,
                            dst_image: np.ndarray,
                            homography: np.ndarray
                            ) -> Tuple[int, int, PadStruct]:
        """Compute the panorama shape and the padding in each axes.

        Args:
            src_image: Source image expected to undergo projective
            transformation.
            dst_image: Destination image to which the source image is being
            mapped to.
            homography: 3x3 Projective Homography matrix.

        For each image we define a struct containing it's corners.
        For the source image we compute the projective transformation of the
        coordinates. If some of the transformed image corners yield negative
        indices - the resulting panorama should be padded with at least
        this absolute amount of pixels.
        The panorama's shape should be:
        dst shape + |the largest negative index in the transformed src index|.

        Returns:
            The panorama shape and a struct holding the padding in each axes (
            row, col).
            panorama_rows_num: The number of rows in the panorama of src to dst.
            panorama_cols_num: The number of columns in the panorama of src to
            dst.
            padStruct = a struct with the padding measures along each axes
            (row,col).
        """
        src_rows_num, src_cols_num, _ = src_image.shape
        dst_rows_num, dst_cols_num, _ = dst_image.shape
        src_edges = {}
        src_edges['upper left corner'] = np.array([1, 1, 1])
        src_edges['upper right corner'] = np.array([src_cols_num, 1, 1])
        src_edges['lower left corner'] = np.array([1, src_rows_num, 1])
        src_edges['lower right corner'] = \
            np.array([src_cols_num, src_rows_num, 1])
        transformed_edges = {}
        for corner_name, corner_location in src_edges.items():
            transformed_edges[corner_name] = homography @ corner_location
            transformed_edges[corner_name] /= transformed_edges[corner_name][-1]
        pad_up = pad_down = pad_right = pad_left = 0
        for corner_name, corner_location in transformed_edges.items():
            if corner_location[1] < 1:
                # pad up
                pad_up = max([pad_up, abs(corner_location[1])])
            if corner_location[0] > dst_cols_num:
                # pad right
                pad_right = max([pad_right,
                                 corner_location[0] - dst_cols_num])
            if corner_location[0] < 1:
                # pad left
                pad_left = max([pad_left, abs(corner_location[0])])
            if corner_location[1] > dst_rows_num:
                # pad down
                pad_down = max([pad_down,
                                corner_location[1] - dst_rows_num])
        panorama_cols_num = int(dst_cols_num + pad_right + pad_left)
        panorama_rows_num = int(dst_rows_num + pad_up + pad_down)
        pad_struct = PadStruct(pad_up=int(pad_up),
                               pad_down=int(pad_down),
                               pad_left=int(pad_left),
                               pad_right=int(pad_right))
        return panorama_rows_num, panorama_cols_num, pad_struct

    @staticmethod
    def add_translation_to_backward_homography(backward_homography: np.ndarray,
                                               pad_left: int,
                                               pad_up: int) -> np.ndarray:
        """Create a new homography which takes translation into account.

        Args:
            backward_homography: 3x3 Projective Homography matrix.
            pad_left: number of pixels that pad the destination image with
            zeros from left.
            pad_up: number of pixels that pad the destination image with
            zeros from the top.

        (1) Build the translation matrix from the pads.
        (2) Compose the backward homography and the translation matrix together.
        (3) Scale the homography as learnt in class.

        Returns:
            A new homography which includes the backward homography and the
            translation.
        """
        # Build the translation matrix from the pads
        trans_matrix = [[1, 0, - pad_left],
                        [0, 1, - pad_up],
                        [0, 0, 1]]

        # Compose the backward homography and the translation matrix
        trans_homography = np.dot(backward_homography, trans_matrix)

        # Scale the homography
        final_homography = trans_homography / (np.linalg.norm(trans_homography))

        return final_homography


    def panorama(self,
                 src_image: np.ndarray,
                 dst_image: np.ndarray,
                 match_p_src: np.ndarray,
                 match_p_dst: np.ndarray,
                 inliers_percent: float,
                 max_err: float) -> np.ndarray:
        """Produces a panorama image from two images, and two lists of
        matching points, that deal with outliers using RANSAC.

        (1) Compute the forward homography and the panorama shape.
        (2) Compute the backward homography.
        (3) Add the appropriate translation to the homography so that the
        source image will plant in place.
        (4) Compute the backward warping with the appropriate translation.
        (5) Create the an empty panorama image and plant there the
        destination image.
        (6) place the backward warped image in the indices where the panorama
        image is zero.
        (7) Don't forget to clip the values of the image to [0, 255].


        Args:
            src_image: Source image expected to undergo projective
            transformation.
            dst_image: Destination image to which the source image is being
            mapped to.
            match_p_src: 2xN points from the source image.
            match_p_dst: 2xN points from the destination image.
            inliers_percent: The expected probability (between 0 and 1) of
            correct match points from the entire list of match points.
            max_err: A scalar that represents the maximum distance (in pixels)
            between the mapped src point to its corresponding dst point,
            in order to be considered as valid inlier.

        Returns:
            A panorama image.

        """
        # Compute the forward homography and shape
        homography = Solution.compute_homography(self, match_p_src, match_p_dst, inliers_percent, max_err)
        panorama_y_cords, panorama_x_cords, pad_stuct = Solution.find_panorama_shape(src_image, dst_image, homography)
        # Compute backward homography
        backward_homography = Solution.compute_homography(self, match_p_dst, match_p_src, inliers_percent,
                                                          max_err)  # compute backward homography
        translated_homography = Solution.add_translation_to_backward_homography(backward_homography, pad_stuct.pad_left, pad_stuct.pad_up)
        backward_map = Solution.compute_backward_mapping(translated_homography, src_image,
                                                         (panorama_y_cords, panorama_x_cords, 3))
        # Create the an empty panorama image and plant the dest image
        img_panorama = np.zeros((panorama_y_cords, panorama_x_cords, 3))
        img_panorama[: backward_map.shape[0], : backward_map.shape[1]] = backward_map
        # place the backward warped image in the indices where the panorama image is zero
        img_panorama[pad_stuct.pad_up: pad_stuct.pad_up + dst_image.shape[0], pad_stuct.pad_left: pad_stuct.pad_left + dst_image.shape[1]] = dst_image

        return np.clip(img_panorama, 0, 255).astype(np.uint8)
