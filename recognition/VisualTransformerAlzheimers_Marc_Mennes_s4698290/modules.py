import torch

#terminology and design choices as per "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale" https://arxiv.org/abs/2010.11929

class Encoder(torch.nn.Module):

    def __init__(self, patchSize, attentionHeads, attentionDropout, networkStructure):
        super().__init__()

        self.norm1 = torch.nn.LayerNorm(patchSize*patchSize)
        self.norm2 = torch.nn.LayerNorm(patchSize*patchSize)

        self.attention = torch.nn.MultiheadAttention(patchSize*patchSize, attentionHeads, dropout = attentionDropout, batch_first=True)

        network = [torch.nn.Linear(patchSize*patchSize, networkStructure[0]), torch.nn.GELU()]

        for i, layer in enumerate(networkStructure):
            if i != len(networkStructure) - 1:
                network.append(torch.nn.Linear(layer, networkStructure[i + 1]))
                network.append(torch.nn.GELU())
            else:
                network.append(torch.nn.Linear(layer, patchSize*patchSize))
        
        self.mlp = torch.nn.Sequential(*network)
        self.dropout = torch.nn.Dropout(0.2)

    def forward(self, imagePatches):

        x = self.norm1(imagePatches)
        x, _ = self.attention(x, x, x, need_weights=False)
        x = self.dropout(x)
        x += imagePatches

        y = self.norm2(x)
        y = self.mlp(y)
        y += x

        return y


class ADNITransformer(torch.nn.Module):

    def __init__(self, nPatches, patchSize, attentionHeads, attentionDropout, classifierHiddenLayers, encoderDenseNetworks):
        super().__init__()
        self.linEmbed = torch.nn.Linear(patchSize*patchSize, patchSize*patchSize)
        self.nPatches = nPatches

        self.classToken = torch.nn.Parameter(torch.rand(1, 1, patchSize*patchSize))

        #build the encoder block
        encoders = []
        for network in encoderDenseNetworks:
            encoders.append(Encoder(patchSize, attentionHeads, attentionDropout, network))
        #this network takes in the embedded image data and runs it through an encoder multiple times
        self.encoderBlock = torch.nn.Sequential(*encoders)

        #build the mlp head that works on the encoder output
        classifiernetwork = [torch.nn.Linear(patchSize*patchSize, classifierHiddenLayers[0]), torch.nn.GELU()]
        for i, layer in enumerate(classifierHiddenLayers):
            if i != len(classifierHiddenLayers) - 1:
                classifiernetwork.append(torch.nn.Linear(layer, classifierHiddenLayers[i + 1]))
                classifiernetwork.append(torch.nn.GELU())
            else:
                classifiernetwork.append(torch.nn.Linear(layer, 1))
                classifiernetwork.append(torch.nn.Sigmoid())

        #the mlp classifier that takes in the class token and outputs the class of the image
        self.mlpClassifier = torch.nn.Sequential(*classifiernetwork)
    
    def forward(self, imagePatches):
        
        #flattens the 2d image data
        imagePatches = torch.flatten(imagePatches, start_dim=3) 
        #lines the patches up along a single dimension
        imagePatches = torch.flatten(imagePatches, start_dim=1, end_dim=2)

        embeddedImagePatches = torch.zeros_like(imagePatches)
        #linearly embed each of the image patches
        for i in range(self.nPatches):
            #add on positional embeddings
            embeddedImagePatches[:, i, :] = self.linEmbed(imagePatches[:, i, :]) + i + 1

        #expand the class token to all samples in batch
        batchedClassToken = self.classToken.expand(embeddedImagePatches.size()[0], -1, -1)
        
        #add the class token to the token sequence
        embeddingsAndClassTokens = torch.cat((batchedClassToken, embeddedImagePatches), dim=1)

        y = self.encoderBlock(embeddingsAndClassTokens)
        
        transformedClassToken = y[:,0]

        classPrediction = self.mlpClassifier(transformedClassToken)

        return classPrediction

class ADNIConvTransformer(torch.nn.Module):
    

    def __init__(self, attentionDropout, classifierHiddenLayers, encoderDenseNetwork):
        super().__init__()
        
        self.downSample = torch.nn.Sequential(torch.nn.Conv2d(1,5,3), torch.nn.BatchNorm2d(32), torch.nn.ReLU(inplace=True), torch.nn.MaxPool2d(2,2),
                                              torch.nn.Conv2d(5,5,3, padding=3), torch.nn.BatchNorm2d(32), torch.nn.ReLU(inplace=True), torch.nn.MaxPool2d(2,2),
                                              torch.nn.Conv2d(5,1,3, stride=2, padding=2), torch.nn.BatchNorm2d(32), torch.nn.ReLU(inplace=True), torch.nn.MaxPool2d(2,2))

        self.transformerBlock = ADNITransformer(256, 1, 1, attentionDropout, classifierHiddenLayers, encoderDenseNetwork)

    def forward(self, image):
        
        downSampledImage = self.downSample(image)
        print(downSampledImage.size())
        downSampledImage = torch.flatten(downSampledImage, start_dim=2)
        return self.transformerBlock(downSampledImage)


        

